/**
 * ModeToggle - one button that cycles light -> dark -> system.
 *
 * The icon shows the current mode (sun / moon / monitor for "follow the OS"),
 * and the tooltip names what the next click does, so the three states are
 * reachable without opening a menu.
 */

import { useEffect, useState } from "react";
import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

import { Button } from "@/components/ui/button";

const CYCLE = ["light", "dark", "system"] as const;
type Mode = (typeof CYCLE)[number];

const LABEL: Record<Mode, string> = {
  light: "Light",
  dark: "Dark",
  system: "System",
};

const ICON: Record<Mode, typeof Sun> = {
  light: Sun,
  dark: Moon,
  system: Monitor,
};

export function ModeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  // next-themes resolves the stored theme on the client; render a stable
  // placeholder first so the icon never flashes the wrong mode.
  useEffect(() => setMounted(true), []);

  const current: Mode = CYCLE.includes(theme as Mode) ? (theme as Mode) : "system";
  const next = CYCLE[(CYCLE.indexOf(current) + 1) % CYCLE.length];
  const Icon = ICON[current];

  if (!mounted) {
    return (
      <Button variant="ghost" size="icon" className="size-7" aria-label="Theme">
        <Sun className="size-4 opacity-0" />
      </Button>
    );
  }

  return (
    <Button
      variant="ghost"
      size="icon"
      className="size-7"
      onClick={() => setTheme(next)}
      title={`Theme: ${LABEL[current]} - click for ${LABEL[next]}`}
      aria-label={`Theme: ${LABEL[current]}. Switch to ${LABEL[next]}.`}
    >
      <Icon className="size-4" />
    </Button>
  );
}
