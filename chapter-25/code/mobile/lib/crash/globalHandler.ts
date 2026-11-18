/**
 * Last line of defence: errors that no component caught. React Native routes them to ErrorUtils.
 * We report first, then hand over to the previous handler so the normal red screen (development)
 * or the crash (release) still happens.
 */
export function installGlobalErrorHandler(report: (error: unknown, isFatal: boolean) => void): void {
  const previous = ErrorUtils.getGlobalHandler();
  ErrorUtils.setGlobalHandler((error, isFatal) => {
    try {
      report(error, Boolean(isFatal));
    } catch {
      // reporting must never make a crash worse
    }
    previous(error, isFatal);
  });
}
