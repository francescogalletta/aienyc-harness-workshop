// Financial Advisor Harness: the helpers on window.FAH (plain script, no framework).
// The components themselves are HTML with fah- classes; see each component's README.

export type StepLineKind = 'tested' | 'result' | 'strong' | undefined;

export interface FAH {
  /** Builds the small tick drawn in front of a "tested" line. */
  tick(): SVGSVGElement;
  /** Sets or replaces a step's second line and plays its arrival. Empty text removes the line. Text is inserted as text. */
  setLine(step: HTMLElement, text: string, kind?: StepLineKind): HTMLElement | null;
  /** Fills the step with the attention colour and plays one ring. Pass false to clear. */
  needsYou(step: HTMLElement, on?: boolean): void;
  /** Selects one step and clears the selection on every other step under root. */
  select(step: HTMLElement | null, root?: ParentNode): void;
  /** Fades a step that was not part of the last answer. Pass false to restore. */
  fade(step: HTMLElement, on?: boolean): void;
  /** Sends one pulse along each .fah-flow in order. Resolves when the last has landed. */
  flow(lines: ArrayLike<Element>, gapMs?: number): Promise<void>;
  /** Marks a clicked number in the chat and selects the step that produced it. */
  trace(num: HTMLElement | null, step: HTMLElement | null, root?: ParentNode): void;
  /** Flips the "On the side" toggle in a composer. Returns true when side mode is on. */
  sideToggle(button: HTMLElement): boolean;
  /** Replays a CSS animation by removing and re-adding a class. */
  restart(el: Element, cls: string): void;
  wait(ms: number): Promise<void>;
}

declare global {
  interface Window { FAH: FAH; }
}
