  async function upload(form: FormData) {
    setUploading(true);
    setMessage(null);
    try {
      docs.add(await api.uploadDocument(form));
    } catch (e) {
      setMessage(describeError(e)); // "That file is too large.", "You have used all of your storage."
    } finally {
      setUploading(false);
    }
  }

  async function handle(result: PickResult) {
    if (result.kind === "picked") return upload(result.form);
    if (result.kind === "invalid") return setMessage(result.message);
    if (result.kind === "permission") {
      Alert.alert(
        "Camera access is off",
        "Allow the camera in Settings to photograph documents.",
        result.outcome === "blocked"
          ? [{ text: "Not now" }, { text: "Open Settings", onPress: () => void Linking.openSettings() }]
          : [{ text: "OK" }],
      );
    }
  }
