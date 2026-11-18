import { MEDIA_LIMITS } from './limits';

export type DictationPhase = 'idle' | 'asking' | 'recording' | 'uploading' | 'error';

export interface DictationState {
  phase: DictationPhase;
  /** Seconds recorded so far. */
  seconds: number;
  /** The last transcript, available after a successful run. */
  text?: string;
  error?: { message: string; canTryAgain: boolean; needsSettings?: boolean };
}

export type DictationEvent =
  | { type: 'press' } // the microphone button
  | { type: 'permission'; granted: boolean }
  | { type: 'tick' } // one second of recording passed
  | { type: 'stop' }
  | { type: 'cancel' }
  | { type: 'uploaded'; text: string }
  | { type: 'failed'; message: string; canTryAgain: boolean };

export const initialDictation: DictationState = { phase: 'idle', seconds: 0 };

/**
 * One small machine decides what the microphone button does. Every button press, timer tick and
 * network answer is an event, so impossible situations (recording twice, uploading while recording,
 * a late answer after cancelling) cannot happen: events that make no sense in a state are ignored.
 */
export function dictationReducer(state: DictationState, event: DictationEvent, maxSeconds: number = MEDIA_LIMITS.maxDictationSeconds): DictationState {
  switch (state.phase) {
    case 'idle':
    case 'error':
      return event.type === 'press' ? { phase: 'asking', seconds: 0 } : state;

    case 'asking':
      if (event.type === 'permission') {
        return event.granted
          ? { phase: 'recording', seconds: 0 }
          : { phase: 'error', seconds: 0, error: { message: 'We need microphone access to hear you. You can allow it in Settings.', canTryAgain: false, needsSettings: true } };
      }
      return event.type === 'cancel' ? initialDictation : state;

    case 'recording':
      if (event.type === 'tick') {
        const seconds = state.seconds + 1;
        return seconds >= maxSeconds ? { phase: 'uploading', seconds } : { ...state, seconds }; // stop by itself at the limit
      }
      if (event.type === 'stop' || event.type === 'press') return { phase: 'uploading', seconds: state.seconds };
      return event.type === 'cancel' ? initialDictation : state; // cancel: nothing is uploaded

    case 'uploading':
      if (event.type === 'uploaded') return { phase: 'idle', seconds: 0, text: event.text };
      if (event.type === 'failed') return { phase: 'error', seconds: 0, error: { message: event.message, canTryAgain: event.canTryAgain } };
      return event.type === 'cancel' ? initialDictation : state; // presses while uploading are ignored
  }
}
