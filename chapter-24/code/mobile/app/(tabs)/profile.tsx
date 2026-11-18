  async function setAvatar(result: PickResult) {
    if (result.kind === "invalid") return setMessage(result.message);
    if (result.kind === "permission") return Alert.alert(/* offer Settings */);
    if (result.kind !== "picked") return; // cancelled
    setBusy(true);
    setMessage(null);
    try {
      setUser(await api.uploadAvatar(result.form)); // the server resizes it and strips GPS data
    } catch (e) {
      setMessage(describeError(e));
    } finally {
      setBusy(false);
    }
  }
