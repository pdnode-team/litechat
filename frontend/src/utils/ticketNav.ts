type Opener = (ticketId: number) => void;

let opener: Opener | null = null;

export function setTicketOpener(next: Opener | null): void {
  opener = next;
}

export function openTicket(ticketId: number): void {
  opener?.(ticketId);
}
