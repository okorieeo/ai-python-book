export function createEndpoints(client: ApiClient, store: TokenStore) {
  return {
    async login(email: string, password: string): Promise<User> {
      const data = await client.post<SignInResponse>(
        "/auth/login",
        { email, password },
        { auth: false }, // no token yet, and a 401 here means "wrong password"
      );
      await store.setTokens({ access: data.access, refresh: data.refresh });
      return data.user;
    },

    me: () => client.get<User>("/me"),

    documents: (offset = 0, limit = 20) =>
      client.get<Page<Document>>("/documents", { query: { offset, limit } }),

    uploadDocument: (form: FormData) =>
      client.request<Document>("POST", "/documents", { form }),

    // ...register, logout, deleteDocument, documentLink, avatar, devices, socketTicket
  };
}
