import pytest
from litestar.testing import AsyncTestClient
from app.main import app

@pytest.mark.asyncio
async def test_auth_setup_admin_and_customer_rbac():
    async with AsyncTestClient(app=app) as client:
        # 1. Weak password rejected
        weak_pwd_res = await client.post("/api/auth/setup-admin", json={
            "email": "admin@test.com",
            "username": "admin_chief",
            "full_name": "Chief Admin",
            "password": "123",  # Too short, no letters
        })
        assert weak_pwd_res.status_code == 400

        # 2. Setup initial system admin -> role is admin
        admin_setup = await client.post("/api/auth/setup-admin", json={
            "email": "first_admin@test.com",
            "username": "admin_chief",
            "full_name": "Chief Admin",
            "password": "adminpassword123",
        })
        assert admin_setup.status_code in (200, 201), admin_setup.text
        admin_data = admin_setup.json()
        assert admin_data["user"]["role"] == "admin"
        admin_token = admin_data["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # 3. Subsequent setup-admin attempt must be rejected (system already initialized)
        second_setup = await client.post("/api/auth/setup-admin", json={
            "email": "attacker@test.com",
            "username": "attacker",
            "full_name": "Attacker",
            "password": "attackerpassword123",
        })
        assert second_setup.status_code in (400, 403)

        # 4. Normal registration always yields customer role
        cust_reg = await client.post("/api/auth/register", json={
            "email": "customer2@test.com",
            "username": "customer2",
            "full_name": "Customer Two",
            "password": "custpassword123",
        })
        assert cust_reg.status_code in (200, 201), cust_reg.text
        cust_user = cust_reg.json()["user"]
        assert cust_user["role"] == "customer"
        cust_id = cust_user["id"]

        # 5. Customer tries to access /api/users -> blocked with 403
        cust_token = cust_reg.json()["access_token"]
        cust_headers = {"Authorization": f"Bearer {cust_token}"}
        forbidden_res = await client.get("/api/users", headers=cust_headers)
        assert forbidden_res.status_code == 403

        # 6. Admin promotes customer2 to agent -> 200 OK
        promote_res = await client.patch(f"/api/users/{cust_id}/role", json={"role": "agent"}, headers=admin_headers)
        assert promote_res.status_code == 200
        assert promote_res.json()["role"] == "agent"

        # 7. Admin deactivates user status
        deact_res = await client.patch(f"/api/users/{cust_id}/status", json={"is_active": False}, headers=admin_headers)
        assert deact_res.status_code == 200
        assert deact_res.json()["is_active"] is False

@pytest.mark.asyncio
async def test_ticket_creation_pure_human_and_isolation():
    async with AsyncTestClient(app=app) as client:
        # Initial Admin
        admin_res = await client.post("/api/auth/setup-admin", json={
            "email": "root@test.com",
            "username": "root_admin",
            "full_name": "Root Admin",
            "password": "adminpassword123",
        })
        admin_h = {"Authorization": f"Bearer {admin_res.json()['access_token']}"}

        # Register two customers
        c1 = await client.post("/api/auth/register", json={
            "email": "c1@test.com",
            "username": "client1",
            "full_name": "Client One",
            "password": "clientpassword123",
        })
        c1_h = {"Authorization": f"Bearer {c1.json()['access_token']}"}
        c1_id = c1.json()["user"]["id"]

        c2 = await client.post("/api/auth/register", json={
            "email": "c2@test.com",
            "username": "client2",
            "full_name": "Client Two",
            "password": "clientpassword123",
        })
        c2_h = {"Authorization": f"Bearer {c2.json()['access_token']}"}

        # C1 creates ticket
        t_res = await client.post("/api/tickets/", json={
            "title": "Broken link on profile billing page",
            "description": "Clicking download receipt gives a blank page.",
            "priority": "medium",
            "category": "billing",
        }, headers=c1_h)
        assert t_res.status_code in (200, 201)
        t_json = t_res.json()
        ticket_id = t_json["id"]
        assert t_json["ticket_code"].startswith("TCK-")

        # Check messages: ONLY customer message, ZERO AI bot messages
        msgs = (await client.get(f"/api/tickets/{ticket_id}/messages", headers=c1_h)).json()
        assert len(msgs) == 1
        assert msgs[0]["sender_role"] == "customer"

        # C2 tries to read C1's ticket -> MUST BE 403 or 404 (IDOR safe)!
        hack_res = await client.get(f"/api/tickets/{ticket_id}", headers=c2_h)
        assert hack_res.status_code in (403, 404)

        # C2 tries to read C1's ticket messages -> MUST BE 403 or 404!
        hack_msg = await client.get(f"/api/tickets/{ticket_id}/messages", headers=c2_h)
        assert hack_msg.status_code in (403, 404)

        # Customer tries to forge whisper message -> MUST BE rejected or downgraded to text
        forged = await client.post(f"/api/tickets/{ticket_id}/messages", json={
            "content": "Trying to sneak an internal note",
            "message_type": "whisper",
        }, headers=c1_h)
        assert forged.status_code in (200, 201)
        assert forged.json()["message_type"] == "text"

        # Agent/Admin assigns ticket -> changes status to in_progress
        assign_res = await client.patch(f"/api/tickets/{ticket_id}/assign", json={
            "agent_id": admin_res.json()["user"]["id"],
        }, headers=admin_h)
        assert assign_res.status_code == 200
        assert assign_res.json()["assigned_agent_id"] == admin_res.json()["user"]["id"]
        assert assign_res.json()["status"] == "in_progress"

        # Unassigning reverts to open
        unassign_res = await client.patch(f"/api/tickets/{ticket_id}/assign", json={
            "agent_id": None,
        }, headers=admin_h)
        assert unassign_res.status_code == 200
        assert unassign_res.json()["assigned_agent_id"] is None
        assert unassign_res.json()["status"] == "open"

        # Customer resolves ticket
        res_res = await client.patch(f"/api/tickets/{ticket_id}/status", json={
            "status": "resolved",
        }, headers=c1_h)
        assert res_res.status_code == 200
        assert res_res.json()["status"] == "resolved"
        assert res_res.json()["resolved_at"] is not None

        # C2 tries to submit CSAT rating on C1's ticket -> 403 Forbidden
        hack_csat = await client.post(f"/api/tickets/{ticket_id}/csat", json={
            "score": 1,
            "comment": "Rogue rating",
        }, headers=c2_h)
        assert hack_csat.status_code == 403

        # C1 submits CSAT rating -> 201 OK
        valid_csat = await client.post(f"/api/tickets/{ticket_id}/csat", json={
            "score": 5,
            "comment": "Great resolution!",
        }, headers=c1_h)
        assert valid_csat.status_code in (200, 201)
        assert valid_csat.json()["customer_id"] == c1_id

@pytest.mark.asyncio
async def test_apps_ticket_types_and_faq_engine():
    async with AsyncTestClient(app=app) as client:
        # 1. Setup Admin
        admin_setup = await client.post("/api/auth/setup-admin", json={
            "email": "superadmin@test.com",
            "username": "superadmin",
            "full_name": "Super Admin",
            "password": "adminpassword123",
        })
        admin_h = {"Authorization": f"Bearer {admin_setup.json()['access_token']}"}

        # 2. Normal customer
        cust_reg = await client.post("/api/auth/register", json={
            "email": "cust@test.com",
            "username": "cust_user",
            "full_name": "Customer User",
            "password": "customerpassword123",
        })
        cust_h = {"Authorization": f"Bearer {cust_reg.json()['access_token']}"}

        # 3. Customer tries to create an app -> 403 Forbidden
        app_fail = await client.post("/api/apps/", json={
            "name": "Hacker App",
            "code": "hacker_app",
        }, headers=cust_h)
        assert app_fail.status_code == 403

        # 4. Admin creates Managed App
        app_res = await client.post("/api/apps/", json={
            "name": "Cloud Dashboard",
            "code": "cloud_dash",
            "base_url": "https://dashboard.example.com",
        }, headers=admin_h)
        assert app_res.status_code in (200, 201)
        app_id = app_res.json()["id"]

        # 5. Admin creates Ticket Type with Custom Fields
        tt_res = await client.post("/api/ticket-types/", json={
            "name": "Bug Report",
            "code": "bug_report",
            "description": "Technical software defects",
            "fields_schema": [
                {
                    "key": "error_code",
                    "label": "Error Code",
                    "type": "text",
                    "required": True,
                    "placeholder": "e.g. ERR_502",
                },
                {
                    "key": "browser",
                    "label": "Browser",
                    "type": "select",
                    "required": False,
                    "options": ["Chrome", "Firefox", "Safari", "Edge"],
                },
            ],
        }, headers=admin_h)
        assert tt_res.status_code in (200, 201)
        tt_id = tt_res.json()["id"]

        # 6. Admin creates FAQ item
        faq_res = await client.post("/api/faq/", json={
            "category": "technical",
            "question": "How to resolve error 502 gateway timeout?",
            "answer": "Please verify upstream server health and restart the worker pool.",
            "keywords": "502,gateway,timeout,nginx",
            "quick_replies": ["Still timeout", "Server restart failed"],
        }, headers=admin_h)
        assert faq_res.status_code in (200, 201)

        # 7. Customer queries FAQ engine
        query_res = await client.post("/api/faq/query", json={
            "query": "502 gateway",
        })
        assert query_res.status_code in (200, 201)
        q_data = query_res.json()
        assert len(q_data["matches"]) >= 1
        assert "Still timeout" in q_data["quick_options"]
        assert q_data["can_escalate_ticket"] is True

        # 8. Customer creates ticket referencing app and ticket type
        ticket_res = await client.post("/api/tickets/", json={
            "title": "Gateway 502 on checkout payment",
            "description": "Getting 502 Bad Gateway during Stripe checkout callback.",
            "priority": "high",
            "category": "technical",
            "app_id": app_id,
            "target_url": "https://dashboard.example.com/checkout",
            "ticket_type_id": tt_id,
            "custom_fields": {
                "error_code": "ERR_502_GATEWAY",
                "browser": "Chrome",
            },
        }, headers=cust_h)
        assert ticket_res.status_code in (200, 201)
        t_data = ticket_res.json()
        assert t_data["app_id"] == app_id
        assert t_data["app"]["name"] == "Cloud Dashboard"
        assert t_data["target_url"] == "https://dashboard.example.com/checkout"
        assert t_data["ticket_type_id"] == tt_id
        assert t_data["ticket_type"]["name"] == "Bug Report"
        assert t_data["custom_fields"]["error_code"] == "ERR_502_GATEWAY"
        assert t_data["custom_fields"]["browser"] == "Chrome"

        # 9. Admin tries to delete app or ticket type while referenced by active ticket -> 400 Bad Request
        del_app_blocked = await client.delete(f"/api/apps/{app_id}", headers=admin_h)
        assert del_app_blocked.status_code == 400
        assert any(word in del_app_blocked.json()["detail"].lower() for word in ["associated", "referenced"])

        del_tt_blocked = await client.delete(f"/api/ticket-types/{tt_id}", headers=admin_h)
        assert del_tt_blocked.status_code == 400
        assert any(word in del_tt_blocked.json()["detail"].lower() for word in ["associated", "referenced"])

@pytest.mark.asyncio
async def test_admin_update_capabilities():
    async with AsyncTestClient(app=app) as client:
        # 1. Setup Admin
        admin = await client.post("/api/auth/setup-admin", json={
            "email": "updater_admin@test.com",
            "username": "up_admin",
            "full_name": "Update Admin",
            "password": "adminpassword123",
        })
        admin_h = {"Authorization": f"Bearer {admin.json()['access_token']}"}

        # 2. Register Customer
        cust = await client.post("/api/auth/register", json={
            "email": "updater_cust@test.com",
            "username": "up_cust",
            "full_name": "Update Cust",
            "password": "customerpassword123",
        })
        cust_h = {"Authorization": f"Bearer {cust.json()['access_token']}"}

        # Create App & Update App
        app_res = await client.post("/api/apps/", json={
            "name": "Initial App",
            "code": "init_app",
            "base_url": "https://init.example.com",
        }, headers=admin_h)
        app_id = app_res.json()["id"]

        # Customer cannot update -> 403
        cust_up_app = await client.put(f"/api/apps/{app_id}", json={"name": "Hacked App"}, headers=cust_h)
        assert cust_up_app.status_code == 403

        # Admin updates app
        admin_up_app = await client.put(f"/api/apps/{app_id}", json={
            "name": "Renamed App",
            "base_url": "https://updated.example.com",
            "is_active": False,
        }, headers=admin_h)
        assert admin_up_app.status_code == 200
        assert admin_up_app.json()["name"] == "Renamed App"
        assert admin_up_app.json()["base_url"] == "https://updated.example.com"
        assert admin_up_app.json()["is_active"] is False

        # Create Ticket Type & Update Ticket Type
        tt_res = await client.post("/api/ticket-types/", json={
            "name": "Incident",
            "code": "incident",
            "description": "Critical issues",
            "fields_schema": [{"key": "severity", "label": "Severity", "type": "text", "required": True}],
        }, headers=admin_h)
        tt_id = tt_res.json()["id"]

        admin_up_tt = await client.put(f"/api/ticket-types/{tt_id}", json={
            "name": "Production Incident",
            "description": "Updated description",
            "fields_schema": [
                {"key": "severity", "label": "Severity Level", "type": "select", "required": True, "options": ["P1", "P2"]},
                {"key": "impact", "label": "Affected Users", "type": "number", "required": False},
            ],
        }, headers=admin_h)
        assert admin_up_tt.status_code == 200
        assert admin_up_tt.json()["name"] == "Production Incident"
        assert len(admin_up_tt.json()["fields_schema"]) == 2
        assert admin_up_tt.json()["fields_schema"][0]["label"] == "Severity Level"

        # Create FAQ & Update FAQ
        faq_res = await client.post("/api/faq/", json={
            "category": "technical",
            "question": "Original Q?",
            "answer": "Original A.",
        }, headers=admin_h)
        faq_id = faq_res.json()["id"]

        admin_up_faq = await client.put(f"/api/faq/{faq_id}", json={
            "question": "Updated Q?",
            "answer": "Updated **Markdown** answer.",
            "keywords": "updated,query",
            "quick_replies": ["Next Step"],
        }, headers=admin_h)
        assert admin_up_faq.status_code == 200
        assert admin_up_faq.json()["question"] == "Updated Q?"
        assert admin_up_faq.json()["quick_replies"] == ["Next Step"]

        # Create Canned Response & Update Canned Response
        canned_res = await client.post("/api/canned-responses/", json={
            "shortcut": "/orig",
            "title": "Orig Macro",
            "content": "Hello original message",
            "category": "greeting",
        }, headers=admin_h)
        canned_id = canned_res.json()["id"]

        admin_up_canned = await client.patch(f"/api/canned-responses/{canned_id}", json={
            "shortcut": "/updated_shortcut",
            "title": "Updated Macro",
            "content": "Updated content text",
        }, headers=admin_h)
        assert admin_up_canned.status_code == 200
        assert admin_up_canned.json()["shortcut"] == "/updated_shortcut"
        assert admin_up_canned.json()["title"] == "Updated Macro"
