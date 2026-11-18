import { useCallback, useRef, useState } from 'react';
import { nextPollDelay } from './pollDelay';
import { apiRequest } from '../lib/api/client';
import { userMessage } from '../lib/net/errors';
import { MEDIA_LIMITS } from '../lib/media/limits';
import { UploadError, uploadFile, type LocalFile } from '../lib/media/upload';

export type AttachmentStage = 'uploading' | 'processing' | 'ready' | 'error';

export interface PendingAttachment {
  localId: string;
  name: string;
  stage: AttachmentStage;
  /** The server's id, once the upload has been accepted. This is what the message refers to. */
  id?: string;
  error?: string;
}

interface ServerAttachment {
  id: string;
  status: 'uploaded' | 'processing' | 'ready' | 'rejected' | 'failed';
  error_code: string;
}

const MAX_POLLS = 40; // a bit over two minutes; then we stop asking and say so

export function useAttachments() {
  const [items, setItems] = useState<PendingAttachment[]>([]);
  const counter = useRef(0);

  const patch = useCallback((localId: string, change: Partial<PendingAttachment>) => {
    setItems((current) => current.map((i) => (i.localId === localId ? { ...i, ...change } : i)));
  }, []);

  const add = useCallback(
    async (file: LocalFile) => {
      if (items.length >= MEDIA_LIMITS.maxAttachmentsPerMessage) return;
      const localId = `local-${++counter.current}`;
      setItems((current) => [...current, { localId, name: file.name, stage: 'uploading' }]);
      try {
        const accepted = await uploadFile<ServerAttachment>('/attachments/', file);
        patch(localId, { id: accepted.id, stage: 'processing' });
        for (let attempt = 0; attempt < MAX_POLLS; attempt++) {
          await new Promise((resolve) => setTimeout(resolve, nextPollDelay(attempt)));
          const current = await apiRequest<ServerAttachment>(`/attachments/${accepted.id}/`);
          if (current.status === 'ready') return patch(localId, { stage: 'ready' });
          if (current.status === 'rejected' || current.status === 'failed') {
            return patch(localId, { stage: 'error', error: new UploadError(current.error_code, '', false).code });
          }
        }
        patch(localId, { stage: 'error', error: 'timeout' });
      } catch (error) {
        patch(localId, { stage: 'error', error: error instanceof UploadError ? error.code : userMessage(error) });
      }
    },
    [items.length, patch],
  );

  const remove = useCallback((localId: string) => setItems((current) => current.filter((i) => i.localId !== localId)), []);
  const readyIds = items.filter((i) => i.stage === 'ready' && i.id).map((i) => i.id as string);
  const busy = items.some((i) => i.stage === 'uploading' || i.stage === 'processing');

  return { items, add, remove, readyIds, busy };
}
