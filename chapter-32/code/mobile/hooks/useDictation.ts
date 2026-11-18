import { requestRecordingPermissionsAsync, setAudioModeAsync, useAudioRecorder } from 'expo-audio';
import { useCallback, useEffect, useReducer } from 'react';
import { userMessage } from '../lib/net/errors';
import { dictationReducer, initialDictation, type DictationEvent, type DictationState } from '../lib/media/dictationState';
import { SPEECH_RECORDING } from '../lib/media/recording';
import { UploadError, uploadFile } from '../lib/media/upload';

// useReducer wants a reducer of exactly (state, event); our function also takes an optional limit, so wrap it.
const reducer = (state: DictationState, event: DictationEvent) => dictationReducer(state, event);

const parseText = (data: unknown): { text: string } => {
  const text = (data as { text?: unknown })?.text;
  if (typeof text !== 'string') throw new Error('unexpected answer');
  return { text };
};

/**
 * Press once to start, press again to stop; the words appear in the text box for the user to check and send.
 * We never send a transcript on the user's behalf: speech recognition makes mistakes, and a human must see them.
 */
export function useDictation(onText: (text: string) => void) {
  const recorder = useAudioRecorder(SPEECH_RECORDING);
  const [state, dispatch] = useReducer(reducer, initialDictation);

  // asking -> ask the system for the microphone, then start recording
  useEffect(() => {
    if (state.phase !== 'asking') return;
    let alive = true;
    void (async () => {
      const permission = await requestRecordingPermissionsAsync();
      if (!alive) return;
      if (permission.granted) {
        await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
        await recorder.prepareToRecordAsync();
        recorder.record();
      }
      dispatch({ type: 'permission', granted: permission.granted });
    })();
    return () => {
      alive = false;
    };
  }, [state.phase, recorder]);

  // recording -> one tick a second; the reducer stops by itself at the limit
  useEffect(() => {
    if (state.phase !== 'recording') return;
    const timer = setInterval(() => dispatch({ type: 'tick' }), 1000);
    return () => clearInterval(timer);
  }, [state.phase]);

  // uploading -> stop the recorder, send the file, report the result
  useEffect(() => {
    if (state.phase !== 'uploading') return;
    const controller = new AbortController();
    void (async () => {
      try {
        await recorder.stop();
        await setAudioModeAsync({ allowsRecording: false });
        const uri = recorder.uri;
        if (!uri) throw new Error('no recording');
        const { text } = await uploadFile('/dictation/', { uri, name: 'dictation.m4a', mimeType: 'audio/mp4' }, { signal: controller.signal, timeoutMs: 45_000, parse: parseText });
        dispatch({ type: 'uploaded', text });
        onText(text);
      } catch (error) {
        if (controller.signal.aborted) return;
        const known = error instanceof UploadError;
        dispatch({ type: 'failed', message: known ? error.message : userMessage(error), canTryAgain: known ? error.canTryAgain : true });
      }
    })();
    return () => controller.abort(); // cancelled or unmounted: the answer is no longer wanted
  }, [state.phase, recorder, onText]);

  const press = useCallback(() => dispatch({ type: 'press' }), []);
  const cancel = useCallback(() => {
    void recorder.stop().catch(() => undefined); // throw the recording away
    dispatch({ type: 'cancel' });
  }, [recorder]);

  return { state, press, cancel };
}
