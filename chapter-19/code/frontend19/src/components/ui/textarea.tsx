import type * as React from "react";
import { cn } from "@/lib/utils";
import { field } from "./field";

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(field, "min-h-16 resize-none", className)}
      {...props}
    />
  );
}

export { Textarea };
