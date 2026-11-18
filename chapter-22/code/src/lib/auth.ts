// A development stand-in: the token lives in memory only.
// Chapter 20 builds the real flow (refresh cookie, route protection).
// The dashboard depends on just this one function.
let accessToken: string | null = null;

export const getAccessToken = () => accessToken;
export const setAccessToken = (token: string | null) => {
  accessToken = token;
};
