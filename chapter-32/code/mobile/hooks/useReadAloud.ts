import { useAudioPlayer, useAudioPlayerStatus } from 'expo-audio';
import * as Speech from 'expo-speech';
import { useCallback, useEffect, useRef, useState } from 'react';
import { apiRequest, getApiConfig } from '../lib/api/client';
import { splitForSpeech, toSpeakable } from '../lib/media/speakable';

/**
 * Read a reply aloud with the phone's own voice: free, private, works offline, and no vendor can retire it.
 * The text is cleaned and cut at sentence ends because speech engines refuse text above a maximum length.
 */
export function useDeviceSpeech() {
  const [speaking, setSpeaking] = useState(false);
  const queue = useRef<string[]>([]);
  const generation = useRef(0); // stop() bumps it, so callbacks from the old reading are ignored

  const next = useCallback((id: number, language?: string) => {
    if (id !== generation.current) return;
    const text = queue.current.shift();
    if (text === undefined) return setSpeaking(false);
    Speech.speak(text, {
      language,
      onDone: () => next(id, language),
      onStopped: () => {
        if (id === generation.current) setSpeaking(false);
      },
      onError: () => {
        if (id === generation.current) setSpeaking(false);
      },
    });
  }, []);

  const stop = useCallback(() => {
    generation.current++;
    queue.current = [];
    Speech.stop();
    setSpeaking(false);
  }, []);

  const speak = useCallback(
    (markdown: string, language?: string) => {
      stop();
      queue.current = splitForSpeech(toSpeakable(markdown), Math.min(Speech.maxSpeechInputLength, 3000));
      if (queue.current.length === 0) return;
      setSpeaking(true);
      next(generation.current, language);
    },
    [next, stop],
  );

  useEffect(() => stop, [stop]); // leaving the screen silences the voice
  return { speak, stop, speaking };
}

/** The better-sounding alternative: the server's voice, played part by part. Costs money per new message. */
export function useServerSpeech(messageId: string) {
  const player = useAudioPlayer(null);
  const status = useAudioPlayerStatus(player);
  const part = useRef(-1);
  const total = useRef(0);
  const [active, setActive] = useState(false);

  const playPart = useCallback(
    (index: number) => {
      const { baseUrl, getToken } = getApiConfig();
      void getToken().then((token) => {
        part.current = index;
        // expo-audio can send headers with a remote source, so the protected endpoint is streamed directly
        player.replace({ uri: `${baseUrl}/messages/${messageId}/speech/?part=${index}`, headers: token ? { Authorization: `Bearer ${token}` } : {} });
        player.play();
      });
    },
    [messageId, player],
  );

  const start = useCallback(async () => {
    const info = await apiRequest<{ parts: number }>(`/messages/${messageId}/speech/?info=1`);
    if (info.parts < 1) return;
    total.current = info.parts;
    setActive(true);
    playPart(0);
  }, [messageId, playPart]);

  useEffect(() => {
    if (!status.didJustFinish) return;
    if (part.current + 1 < total.current) playPart(part.current + 1);
    else setActive(false);
  }, [status.didJustFinish, playPart]);

  const stop = useCallback(() => {
    player.pause();
    total.current = 0;
    setActive(false);
  }, [player]);

  return { start, stop, active };
}
