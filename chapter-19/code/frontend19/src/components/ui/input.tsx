import type * as React from "react";
import { cn } from "@/lib/utils";
import { field } from "./field";

function Input({ className, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      data-slot="input"
      className={cn(field, "h-10", className)}
      {...props}
    />
  );
}

export { Input };
