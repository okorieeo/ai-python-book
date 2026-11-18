<Pressable
  accessibilityRole="button"
  accessibilityLabel="Stop generating"
  accessibilityHint="Stops the assistant's current answer"
  onPress={stop}
  hitSlop={12}                       // enlarges the touch area without changing the look
>
  <Text>Stop</Text>
</Pressable>
