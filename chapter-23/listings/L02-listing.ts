const styles = StyleSheet.create({
  card: {
    padding: 16,               // points, not px
    borderRadius: 12,
    backgroundColor: "#f1f5f9",
    gap: 8,                    // space between children (like CSS gap)
  },
});

<View style={styles.card} />                       // one style
<View style={[styles.card, { opacity: 0.5 }]} />   // an array: later entries win
