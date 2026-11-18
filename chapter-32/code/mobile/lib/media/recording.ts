import { AudioQuality, IOSOutputFormat, type RecordingOptions } from 'expo-audio';

/**
 * Settings made for SPEECH: mono, 16 kHz, AAC in an .m4a file, about 6 KB per second.
 * Do not use the built-in presets for dictation: HIGH_QUALITY is 44.1 kHz stereo (several times the data for
 * no gain in accuracy) and LOW_QUALITY records a narrow-band 3GP/AMR file on Android, which hurts accuracy.
 */
export const SPEECH_RECORDING: RecordingOptions = {
  extension: '.m4a',
  sampleRate: 16000,
  numberOfChannels: 1,
  bitRate: 48000,
  android: { outputFormat: 'mpeg4', audioEncoder: 'aac' },
  ios: { outputFormat: IOSOutputFormat.MPEG4AAC, audioQuality: AudioQuality.MEDIUM },
  web: { mimeType: 'audio/webm', bitsPerSecond: 48000 },
};
