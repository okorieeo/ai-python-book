"use client";

import { useId, useState } from "react";
import { MAX_MESSAGE_LENGTH } from "@/lib/chat/protocol";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

type Props = { onSend: (content: string) => boolean; disabled: boolean };

export function Composer({ onSend, disabled }: Props) {
  const id = useId();
  const [value, setValue] = useState("");

  function submit() {
    if (onSend(value)) setValue("");
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
      className="flex gap-2 border-t border-border p-3"
    >
      <label htmlFor={id} className="sr-only">
        Message
      </label>
      <Textarea
        id={id}
        rows={1}
        value={value}
        maxLength={MAX_MESSAGE_LENGTH}
        placeholder="Ask something…"
        disabled={disabled}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          // Enter sends, Shift+Enter adds a line. Never hijack Enter while an IME is composing.
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            submit();
          }
        }}
      />
      <Button type="submit" disabled={disabled || value.trim() === ""}>
        Send
      </Button>
    </form>
  );
}
