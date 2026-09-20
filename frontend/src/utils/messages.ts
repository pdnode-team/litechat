import type { Message } from '../types';

/**
 * Append a message that arrived over the WebSocket, ignoring one already present.
 *
 * The same frame can arrive twice (a reconnect replaying the last event, or an
 * optimistic local echo that the server later broadcasts), and action cards ride
 * along with the `ticket_updated` frame of the mutation that produced them.
 */
export function mergeMessage(messages: Message[], incoming: Message): Message[] {
  if (messages.some((message) => message.id === incoming.id)) return messages;
  return [...messages, incoming];
}
