/**
 * Limits the phone applies BEFORE uploading, to save the user's time and data. The server enforces its own
 * limits regardless (Chapter 32, section 32.3): these only make the common case fast and the errors early.
 */
export const MEDIA_LIMITS = {
  /** Longest side of a picture we upload. Matches what the model can use, so more pixels are wasted data. */
  maxImageEdge: 1568,
  jpegQuality: 0.8,
  maxImageBytes: 10 * 1024 * 1024,
  maxPdfBytes: 20 * 1024 * 1024,
  maxDictationSeconds: 60,
  maxAttachmentsPerMessage: 5,
} as const;
