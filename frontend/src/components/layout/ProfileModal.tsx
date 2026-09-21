import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { authApi, usersApi } from '../../api/client';
import { apiErrorMessage, fieldErrorMap } from '../../utils/errors';
import { Modal } from '../common/Modal';
import { UserAvatar } from '../common/UserAvatar';
import { useToast } from '../common/Toast';

export const ProfileModal: React.FC<{ isOpen: boolean; onClose: () => void }> = ({ isOpen, onClose }) => {
  const { user, refreshUser } = useAuth();
  const { showSuccess, showError } = useToast();
  const [fullName, setFullName] = useState(user?.full_name ?? '');
  const [avatarUrl, setAvatarUrl] = useState(user?.avatar_url ?? '');
  const [profileBusy, setProfileBusy] = useState(false);
  const [profileErrors, setProfileErrors] = useState<Record<string, string>>({});

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [passwordBusy, setPasswordBusy] = useState(false);

  const [emailPassword, setEmailPassword] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [emailBusy, setEmailBusy] = useState(false);

  if (!user) return null;

  const saveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileBusy(true);
    setProfileErrors({});
    try {
      const updated = await usersApi.updateMe({ full_name: fullName.trim(), avatar_url: avatarUrl.trim() });
      await refreshUser();
      setFullName(updated.full_name);
      setAvatarUrl(updated.avatar_url ?? '');
      showSuccess('Profile updated.');
    } catch (err) {
      const mapped = fieldErrorMap(err);
      if (Object.keys(mapped).length) setProfileErrors(mapped);
      else showError(apiErrorMessage(err, 'Could not update your profile.'));
    } finally {
      setProfileBusy(false);
    }
  };

  const savePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordBusy(true);
    try {
      const res = await authApi.changePassword(currentPassword, newPassword);
      localStorage.setItem('litechat_token', res.access_token);
      await refreshUser();
      setCurrentPassword('');
      setNewPassword('');
      showSuccess('Password updated.');
    } catch (err) {
      showError(apiErrorMessage(err, 'Could not change your password.'));
    } finally {
      setPasswordBusy(false);
    }
  };

  const saveEmail = async (e: React.FormEvent) => {
    e.preventDefault();
    setEmailBusy(true);
    try {
      const res = await authApi.changeEmail(emailPassword, newEmail.trim());
      setEmailPassword('');
      setNewEmail('');
      showSuccess(res.detail);
    } catch (err) {
      showError(apiErrorMessage(err, 'Could not start the email change.'));
    } finally {
      setEmailBusy(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} label="Your profile" panelClassName="w-full max-w-md bg-zinc-950 border border-zinc-800 rounded-xl p-5 space-y-5">
      <div className="flex items-center gap-3">
        <UserAvatar name={fullName || user.full_name} src={avatarUrl || user.avatar_url} size="lg" />
        <div>
          <h2 className="text-sm font-semibold text-zinc-100">Your profile</h2>
          <p className="text-[11px] font-mono text-zinc-500">{user.email}</p>
        </div>
      </div>

      <form onSubmit={saveProfile} className="space-y-3">
        <label className="block">
          <span className="block text-[10px] font-mono uppercase text-zinc-500 mb-1">Display name</span>
          <input
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            maxLength={150}
            required
            minLength={2}
            className={inputClass}
          />
          {profileErrors.full_name && <p className="text-[11px] text-rose-400 mt-1">{profileErrors.full_name}</p>}
        </label>
        <label className="block">
          <span className="block text-[10px] font-mono uppercase text-zinc-500 mb-1">Avatar URL</span>
          <input
            value={avatarUrl}
            onChange={(e) => setAvatarUrl(e.target.value)}
            maxLength={500}
            placeholder="https://…"
            className={inputClass}
          />
          {profileErrors.avatar_url && <p className="text-[11px] text-rose-400 mt-1">{profileErrors.avatar_url}</p>}
        </label>
        <button type="submit" disabled={profileBusy} className={buttonClass}>
          {profileBusy ? 'Saving…' : 'Save profile'}
        </button>
      </form>

      <form onSubmit={savePassword} className="space-y-3 border-t border-zinc-800 pt-4">
        <p className="text-[10px] font-mono uppercase text-zinc-500">Change password</p>
        <input
          type="password"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          placeholder="Current password"
          required
          className={inputClass}
        />
        <input
          type="password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          placeholder="New password"
          required
          minLength={8}
          className={inputClass}
        />
        <button type="submit" disabled={passwordBusy} className={buttonClass}>
          {passwordBusy ? 'Updating…' : 'Update password'}
        </button>
      </form>

      <form onSubmit={saveEmail} className="space-y-3 border-t border-zinc-800 pt-4">
        <p className="text-[10px] font-mono uppercase text-zinc-500">Change email</p>
        <p className="text-[11px] text-zinc-500">We will write to the new address and notify the old one. The change is not applied until you confirm.</p>
        <input
          type="email"
          value={newEmail}
          onChange={(e) => setNewEmail(e.target.value)}
          placeholder="New email"
          required
          className={inputClass}
        />
        <input
          type="password"
          value={emailPassword}
          onChange={(e) => setEmailPassword(e.target.value)}
          placeholder="Current password"
          required
          className={inputClass}
        />
        <button type="submit" disabled={emailBusy} className={buttonClass}>
          {emailBusy ? 'Sending…' : 'Send confirmation'}
        </button>
      </form>
    </Modal>
  );
};

const inputClass =
  'w-full text-xs px-2.5 py-1.5 bg-zinc-950 border border-zinc-800 rounded-md text-zinc-100 focus:border-zinc-600 focus:outline-none';
const buttonClass =
  'w-full text-xs font-medium py-1.5 rounded-md bg-zinc-100 text-zinc-900 hover:bg-white disabled:opacity-50';
