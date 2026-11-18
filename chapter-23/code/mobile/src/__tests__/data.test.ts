import { createConversation, getConversation, listConversations, sendMessage } from '@/lib/data';

describe('the mock data layer', () => {
  it('starts with two conversations, newest activity first', async () => {
    const list = await listConversations();
    expect(list.map((c) => c.id).sort()).toEqual(['invoices', 'welcome']);
  });

  it('creates an empty conversation', async () => {
    const created = await createConversation();
    expect(created.lastMessage).toBeNull();
    expect((await getConversation(created.id))?.messages).toEqual([]);
  });

  it('adds the question and the answer, and updates the list preview', async () => {
    const { userMessage, assistantMessage } = await sendMessage('welcome', 'Hello');
    expect(userMessage).toMatchObject({ role: 'user', content: 'Hello' });
    expect(assistantMessage.content).toBe('Echo: Hello');
    const list = await listConversations();
    expect(list[0]).toMatchObject({ id: 'welcome', lastMessage: 'Echo: Hello' }); // moved to the top
  });

  it('rejects for an unknown conversation', async () => {
    await expect(sendMessage('missing', 'Hi')).rejects.toThrow('not found');
    expect(await getConversation('missing')).toBeNull();
  });
});
