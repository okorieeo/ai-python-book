"use client";

import { Menu } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";

/** On small screens the sidebar lives in a slide-in panel opened by a button. */
export function MobileNav({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="md:hidden">
          <Menu aria-hidden="true" />
          <span className="sr-only">Open conversations</span>
        </Button>
      </SheetTrigger>
      <SheetContent>
        <SheetTitle>Conversations</SheetTitle>
        <SheetDescription className="sr-only">
          Choose a conversation or start a new one.
        </SheetDescription>
        {/* Close the panel when any link inside it is followed. */}
        <div
          className="flex flex-col gap-4"
          onClick={(event) => {
            if ((event.target as HTMLElement).closest("a")) setOpen(false);
          }}
        >
          {children}
        </div>
      </SheetContent>
    </Sheet>
  );
}
