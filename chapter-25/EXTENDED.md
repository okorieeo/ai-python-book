# Chapter 25 — Mobile UX and Performance: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## Knowing Whether You Are Online › One source of truth

Several parts of the app need to know whether we are online: the query cache, the outbox flusher, the banner and the socket. If each asked NetInfo in its own way they would disagree. Instead we feed NetInfo’s verdict into TanStack Query’s `onlineManager` once, at startup, and everything else follows it. We do the same for the app’s foreground state with `focusManager`, so a stale screen refreshes when the user comes back to the app.

**mobile/lib/net/setupManagers.ts**

```
import NetInfo from '@react-native-community/netinfo';
import { focusManager, onlineManager } from '@tanstack/react-query';
import { AppState } from 'react-native';
import { isOnline } from './connectivity';

/**
 * Call once at startup, before the first render. Makes NetInfo the single source
     of truth for
 * "are we online?" and the app's foreground state the source of truth for "is the
     user looking?".
 */
export function setupNetworkManagers(apiBaseUrl: string): void {
  NetInfo.configure({
    // Ask OUR server whether the internet works, not the phone's idea of it.
        Captive portals and
    // networks that block the system's own check then show up as offline when they
        really are.
    reachabilityUrl: `${apiBaseUrl}/health/`,
    reachabilityTest: async (response) => response.status === 200,
    reachabilityLongTimeout: 60_000, // while reachable: check once a minute
    reachabilityShortTimeout: 5_000, // while unreachable: check every 5 s
    reachabilityRequestTimeout: 10_000,
    useNativeReachability: false, // use the probe above on iOS and Android too
  });

  onlineManager.setEventListener((setOnline) => NetInfo.addEventListener((state) =>
      setOnline(isOnline(state))));

  focusManager.setEventListener((handleFocus) => {
    const subscription = AppState.addEventListener('change', (status) =>
        handleFocus(status === 'active'));
    return () => subscription.remove();
  });
}
```

Two choices in `NetInfo.configure` deserve an explanation. First, `reachabilityUrl` points at **our own** health endpoint, and `useNativeReachability: false` makes NetInfo use that probe on iOS and Android too. The phone’s built-in idea of “internet works” can differ from “our server works”, and our server is the only thing the app cares about. Second, the timeouts say how often to check: roughly once a minute while things are fine, and every few seconds while we think we are offline, so the app notices quickly when the network comes back. Tune these numbers: each check is one small request.

> **The health endpoint must be public, cheap and return exactly 200**
>
> `reachabilityTest` above accepts only status 200. Chapter 17 listed the health check among the public endpoints, so it needs no login. It must also be **cheap** (no heavy database work, because every phone calls it every minute) and lightly throttled. If it ever returns 301, 401 or 400 (for example a host name missing from `ALLOWED_HOSTS`), every phone will believe it is offline and your queries will pause. The troubleshooting table in 25.8 lists this first.

There is one more rule that no library can follow for you: **a request is the real test**. NetInfo can be wrong, and a probe can pass while the next request fails. So the code never refuses to try because it thinks it is offline; it uses the online state to pause retries and to tell the user, and lets the request report what actually happened (25.7).


## Writing While Offline: The Outbox › Sending and flushing

Sending is three lines: make an id, save to the outbox, ask for a flush. The flusher runs once, near the root, and tries to send whenever something could newly succeed: at app start, when the network returns, when the user comes back to the app, and every 30 seconds for items whose waiting time is over.

**mobile/hooks/useSendMessage.ts**

```
import * as Crypto from 'expo-crypto';
import { useCallback } from 'react';
import { SEND_MESSAGE_KIND, type SendMessagePayload } from
    '../lib/offline/messages';
import { outbox } from '../lib/offline/outboxInstance';

/** Returns a function that saves the message to the outbox (instantly) and starts
    sending it. */
export function useSendMessage(conversationId: string) {
  return useCallback(
    async (text: string): Promise<void> => {
      const content = text.trim();
      if (!content) return;
      const payload: SendMessagePayload = { content };
      await outbox.enqueue({ id: Crypto.randomUUID(), kind: SEND_MESSAGE_KIND,
          scope: conversationId, payload });
      void outbox.flush(); // the UI already shows the message as "sending"
    },
    [conversationId],
  );
}
```

**mobile/hooks/useOutboxFlusher.ts**

```
import NetInfo from '@react-native-community/netinfo';
import { useEffect } from 'react';
import { AppState } from 'react-native';
import { isOnline } from '../lib/net/connectivity';
import { outbox } from '../lib/offline/outboxInstance';

/** Mount once, near the root. Tries to send the queue whenever it could newly
    succeed. */
export function useOutboxFlusher(): void {
  useEffect(() => {
    const flush = () => void outbox.flush();

    void outbox.load().then(flush); // app start: finish what the last session left
        behind
    const unsubscribeNet = NetInfo.addEventListener((state) => {
      if (isOnline(state)) flush(); // the network came back
    });
    const appState = AppState.addEventListener('change', (status) => {
      if (status === 'active') flush(); // the user came back
    });
    const timer = setInterval(flush, 30_000); // items whose backoff has expired;
        cheap when nothing is due

    return () => {
      unsubscribeNet();
      appState.remove();
      clearInterval(timer);
    };
  }, []);
}
```

The singleton that connects the outbox to storage, the API and the cache is short. Note what `sendItem` sends: the item’s own id as `client_id`.

**mobile/lib/offline/outboxInstance.ts**

```
import AsyncStorage from '@react-native-async-storage/async-storage';
import { apiRequest } from '../api/client';
import { queryClient } from '../query/client';
import { SEND_MESSAGE_KIND, type SendMessagePayload } from './messages';
import { Outbox, type OutboxItem } from './outbox';

/** Sends one queued item. The item id travels as client_id: the server's
    idempotency key. */
async function sendItem(item: OutboxItem): Promise<unknown> {
  if (item.kind === SEND_MESSAGE_KIND) {
    const { content } = item.payload as SendMessagePayload;
    return apiRequest(`/conversations/${item.scope}/messages/`, {
      method: 'POST',
      body: { client_id: item.id, content },
      idempotent: true,
    });
  }
  throw new Error(`Unknown outbox kind: ${item.kind}`);
}

export const outbox = new Outbox({
  storage: AsyncStorage,
  send: sendItem,
  onSent: (item) => {
    if (item.kind === SEND_MESSAGE_KIND) void queryClient.invalidateQueries({
        queryKey: ['messages', item.scope] });
  },
});
```

> **What about TanStack Query’s own offline mutations?**
>
> TanStack Query can pause mutations while offline and even save them across restarts. It is a good fit for simple cases, such as toggling a favourite. It needs some care: functions cannot be saved to storage, so you register each mutation’s function by key before the saved state is restored. We chose a hand-made outbox for chat because we need strict order per conversation, an idempotency key we control, a per-message “failed” state with retry and delete, and rules that are easy to unit-test without React.


## The Server Must Cooperate: Idempotent Writes › The service: create once, however many times it is sent

The service looks for an existing message first (the fast path) and otherwise inserts. If two copies race, the database constraint lets one win and raises `IntegrityError` for the other; the loser then reads the winner’s row. If the same `client_id` arrives with *different* content, that is never a retry, so it is refused with a conflict.

**chat/services.py (added)**

```
"""ADD to your chat/services.py (Chapter 11, extended in Chapter 17). New in
    Chapter 25: idempotent sends."""
import uuid

from django.db import IntegrityError, transaction

from .models import Conversation, Message

class ClientIdReused(Exception):
    """The same client_id arrived with different content: a client bug or
        tampering, never a retry."""

def _find_by_client_id(conversation: Conversation, client_id: uuid.UUID) -> Message
    | None:
    return Message.objects.filter(conversation=conversation,
        client_id=client_id).first()

def create_user_message(
    *, user, conversation: Conversation, content: str, client_id: uuid.UUID | None
        = None
) -> tuple[Message, bool]:
    """Create the user's message once, however many times the phone sends it.

    Returns (message, created). created is False when this client_id was already
        stored,
    which is how a retry after a lost response looks. Safe under concurrent
        duplicates.
    """
    if conversation.user_id != user.id:
        raise Conversation.DoesNotExist  # services never trust the caller to have
            checked ownership

    if client_id is None:  # web client or an old app version: no retry protection,
        same as before
        return Message.objects.create(conversation=conversation, role="user",
            content=content), True

    existing = _find_by_client_id(conversation, client_id)
    if existing is None:
        try:
            with transaction.atomic():  # a savepoint, so an IntegrityError does
                not poison an outer transaction
                message = Message.objects.create(
                    conversation=conversation, role="user", content=content,
                        client_id=client_id
                )
            return message, True
        except IntegrityError:
            # Two copies of the same send raced and the other one won. The database
                decided; read its answer.
            existing = _find_by_client_id(conversation, client_id)
            if existing is None:
                raise  # a different integrity problem: do not hide it

    if existing.content != content:
        raise ClientIdReused
    return existing, False
```

> **Check first, but let the database decide**
>
> A lookup followed by an insert is not safe on its own: two requests can both find nothing and both insert. The unique constraint is what makes the code correct under concurrency; the lookup only makes the common case cheap. The `transaction.atomic()` block creates a savepoint, so a failed insert does not poison an outer transaction.


## The Server Must Cooperate: Idempotent Writes › The view

The view looks up the conversation through the owner (Chapter 17, section 17.3: someone else’s conversation is a 404), validates the input, and answers 201 for a new message or 200 for a repeat. Both answers contain the same message, so the phone’s merge logic works with either.

**chat/views.py**

```
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import Conversation
from .serializers import MessageCreateSerializer, MessageSerializer

class MessageCreateView(APIView):
    """POST /conversations/<public_id>/messages/  with {"client_id": "<uuid>",
        "content": "..."}

    201 = stored now. 200 = this client_id was stored earlier (a retry); the same
        message is returned.
    409 = the client_id was used before with different content.
    Add your Chapter 17 throttle classes here (throttle_classes = [...]).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):
        # Owner-scoped lookup (Chapter 17, section 17.3): someone else's
            conversation is a 404, not a 403.
        conversation = get_object_or_404(Conversation, public_id=conversation_id,
            user=request.user)
        data = MessageCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)

        try:
            message, created = services.create_user_message(
                user=request.user,
                conversation=conversation,
                content=data.validated_data["content"],
                client_id=data.validated_data.get("client_id"),
            )
        except services.ClientIdReused:
            return Response({"detail": "This client_id was already used for a
                different message."}, status=status.HTTP_409_CONFLICT)

        return Response(MessageSerializer(message).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
```

**chat/serializers.py**

```
from rest_framework import serializers

from .models import Message

MAX_MESSAGE_LENGTH = 8_000  # keep in step with the limit you chose in Chapter 17,
    section 17.7

class MessageCreateSerializer(serializers.Serializer):
    content = serializers.CharField(max_length=MAX_MESSAGE_LENGTH,
        trim_whitespace=True)
    client_id = serializers.UUIDField(required=False)

class MessageSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = Message
        fields = ["id", "role", "content", "created_at", "client_id"]
```

| **Answer** | **Meaning** | **What the phone does** |
|---|---|---|
| **201 Created** | Stored just now | Removes the item from the outbox |
| **200 OK** | This `client_id` was stored earlier (a retry) | The same: removes the item. Nothing is duplicated |
| **409 Conflict** | Same `client_id`, different content | Marks the item failed. It is a bug, never a retry |
| **400 Bad Request** | Invalid input (not a UUID, empty, too long) | Marks the item failed with a clear reason |
| **401 Unauthorized** | Token refused | Keeps everything, stops flushing, asks the user to sign in |
| **404 Not Found** | Not the user’s conversation, or it was deleted | Marks the item failed |
| **429 Too Many Requests** | Chapter 17’s throttle fired | Waits at least as long as `Retry-After` says |

> **Do not bill twice**
>
> **Start the AI reply only when** `created` **is** `True`**.** In your Chapter 14 and Chapter 29 code, the model call begins after the user’s message is stored. If that step also runs for a repeated request, every retry asks the model again and spends tokens twice. Branch on the `created` flag returned by `create_user_message`, and keep the daily token budget from Chapter 17 as a second line of defence.

Add your Chapter 17 throttle classes to the view. They already answer with 429 and a `Retry-After` header, and the client honours it (25.7).


## The Server Must Cooperate: Idempotent Writes › Proving it

**chat/test_idempotency.py (excerpt)**

```
def test_a_retry_returns_the_same_message_and_creates_nothing(self):
    client_id = uuid.uuid4()
    first = self.send(client_id)
    second = self.send(client_id)
    third = self.send(client_id)
    self.assertEqual((first.status_code, second.status_code, third.status_code),
        (201, 200, 200))
    self.assertEqual(first.data["id"], second.data["id"])
    self.assertEqual(Message.objects.count(), 1)

def test_same_client_id_with_different_content_is_rejected(self):
    client_id = uuid.uuid4()
    self.send(client_id, "original")
    response = self.send(client_id, "something else")
    self.assertEqual(response.status_code, 409)
    self.assertEqual(Message.objects.get().content, "original")

def test_a_race_between_two_copies_ends_with_one_message(self):
    """Copy A passes the 'already stored?' check, then copy B stores the message
        first."""
    client_id = uuid.uuid4()
    winner = Message.objects.create(conversation=self.conversation, role="user",
        content="hello", client_id=client_id)
    real_find = services._find_by_client_id
    looks = []

    def find(conversation, cid):
        looks.append(cid)
        return None if len(looks) == 1 else real_find(conversation, cid)  # first
            look: "not stored yet"

    with mock.patch.object(services, "_find_by_client_id", side_effect=find):
        message, created = services.create_user_message(
            user=self.ada, conversation=self.conversation, content="hello",
                client_id=client_id
        )
    self.assertEqual(len(looks), 2)  # it looked, failed to insert, then looked
        again
    self.assertFalse(created)
    self.assertEqual(message.pk, winner.pk)
    self.assertEqual(Message.objects.count(), 1)
```

**bash terminal**

```bash
python manage.py test chat.test_idempotency
```

**Check:** the output ends with `Ran 11 tests` and `OK` (your own project may print a different count if it runs more tests in that module).

Keep `client_id` optional. The web client and any app version that is already installed on a phone do not send it, and they must keep working exactly as before. You will meet that rule again in Chapter 26, where old app versions stay in use for months.


## Slow Networks: Timeouts, Retries and Backoff › A deadline for every request

`fetchWithTimeout` gives every request a deadline and always rejects with an `ApiError`. `requestJson` builds on it and has one more job that is easy to miss: its deadline covers **the body as well as the headers**. A server that sends headers and then stalls would otherwise leave the app waiting after `fetch` has already “succeeded”. We use a plain timer instead of `AbortSignal.timeout()` so the behaviour is the same in every React Native version and we always know whether the timer or the caller cancelled the request.

**mobile/lib/net/fetchWithTimeout.ts**

```
import { ApiError } from './errors';

export const DEFAULT_TIMEOUT_MS = 15_000;

export interface FetchOptions extends Omit<RequestInit, 'signal'> {
  /** Cancels the request from outside, for example when a screen closes. */
  signal?: AbortSignal | null;
  /** The whole attempt must finish within this time (default 15 s). */
  timeoutMs?: number;
  /** Swap in a fake (tests) or a "chaos" fetch (development). */
  fetchImpl?: typeof fetch;
}

/**
 * Runs `run` with an AbortSignal that fires when the time is up or when the caller
     cancels.
 * We use a plain timer instead of AbortSignal.timeout() so it behaves the same in
     every
 * React Native version, and so we always know which of the two caused the abort.
 */
async function runWithDeadline<T>(
  timeoutMs: number,
  outer: AbortSignal | null | undefined,
  run: (signal: AbortSignal) => Promise<T>,
): Promise<T> {
  if (outer?.aborted) throw new ApiError({ kind: 'aborted' });
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const onOuterAbort = () => controller.abort();
  outer?.addEventListener('abort', onOuterAbort, { once: true });

  try {
    return await run(controller.signal);
  } catch (error) {
    if (error instanceof ApiError) throw error; // already classified (http, parse)
    if (timedOut) throw new ApiError({ kind: 'timeout', cause: error });
    if (controller.signal.aborted) throw new ApiError({ kind: 'aborted', cause:
        error });
    throw new ApiError({ kind: 'network', cause: error });
  } finally {
    clearTimeout(timer);
    outer?.removeEventListener('abort', onOuterAbort);
  }
}

/** Like fetch, but never waits forever and always rejects with an ApiError. Time
    ends when headers arrive. */
export function fetchWithTimeout(url: string, options: FetchOptions = {}):
    Promise<Response> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, signal, fetchImpl = fetch, ...init } =
      options;
  return runWithDeadline(timeoutMs, signal, (s) => fetchImpl(url, { ...init,
      signal: s }));
}

/** "30" (seconds) or an HTTP date. Returns milliseconds, or undefined when missing
    or invalid. */
export function parseRetryAfter(value: string | null, now: number = Date.now()):
    number | undefined {
  if (!value) return undefined;
  const trimmed = value.trim();
  if (/^\d+$/.test(trimmed)) return Number(trimmed) * 1000;
  const date = Date.parse(trimmed);
  return Number.isNaN(date) ? undefined : Math.max(0, date - now);
}

export interface JsonOptions<T> extends FetchOptions {
  /** Validate or convert the decoded JSON. Throw to reject it. */
  parse?: (data: unknown) => T;
}

/**
 * Fetch JSON with ONE deadline that covers the headers AND the body. A server that
     sends
 * headers and then stalls would otherwise hang the app after fetch() has already
     "succeeded".
 */
export function requestJson<T = unknown>(url: string, options: JsonOptions<T> =
    {}): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, signal, fetchImpl = fetch, parse, ...init
      } = options;
  return runWithDeadline(timeoutMs, signal, async (s) => {
    const response = await fetchImpl(url, { ...init, signal: s });
    const text = await response.text();

    if (!response.ok) {
      let body: unknown;
      try {
        body = JSON.parse(text);
      } catch {
        body = undefined; // an HTML error page from a proxy: do not keep it
      }
      throw new ApiError({
        kind: 'http',
        status: response.status,
        body,
        retryAfterMs: parseRetryAfter(response.headers.get('retry-after')),
      });
    }
    if (response.status === 204 || text === '') return undefined as T;

    let data: unknown;
    try {
      data = JSON.parse(text);
    } catch (cause) {
      // Typical cause: a captive-portal or proxy page answered with 200 and HTML.
      throw new ApiError({ kind: 'parse', cause });
    }
    try {
      return parse ? parse(data) : (data as T);
    } catch (cause) {
      throw new ApiError({ kind: 'parse', message: 'The response did not have the
          expected shape', cause });
    }
  });
}
```

| **Kind of request** | **Starting deadline** | **Note** |
|---|---|---|
| Connectivity probe (health) | 5 to 10 s | Set in `NetInfo.configure` |
| Normal API call | 15 s (our default) | Raise it only with a reason |
| Lists and search | 20 s | Slow queries on the server deserve a look first |
| File upload (Chapter 16) | Grows with file size | Show progress and allow cancel |
| Streaming AI reply | No total deadline | Use an idle timeout instead: no data for 20 to 30 s means the stream is dead |

These are starting points, not laws. Measure your own API on a slow connection and adjust.

**mobile/__tests__/fetchWithTimeout.test.ts (excerpt)**

```
it('gives up on a connection that never answers', async () => {
  const started = Date.now();
  await assert.rejects(fetchWithTimeout('https://x.test/', { timeoutMs: 30,
      fetchImpl: hangingFetch }), kind('timeout'));
  assert.ok(Date.now() - started < 500);
});

it('the deadline also covers a body that stalls after the headers arrived', async
    () => {
  const stalling: typeof fetch = async (_url, init) =>
    ({
      ok: true,
      status: 200,
      headers: new Headers(),
      text: () => new Promise<string>((_res, rej) =>
          init?.signal?.addEventListener('abort', () => rej(abortError()))),
    }) as unknown as Response;
  await assert.rejects(requestJson('https://x.test/', { timeoutMs: 30, fetchImpl:
      stalling }), kind('timeout'));
});
```


## Slow Networks: Timeouts, Retries and Backoff › Retry in exactly one place

Every layer that retries multiplies the others. TanStack Query retries failed queries (three times by default). If your API function also retried four times, one failed refresh would send up to twelve requests. So each request path has exactly one owner of retrying.

| **Request path** | **Who retries** | **Setting** |
|---|---|---|
| Reads (screens) | TanStack Query | `queryRetry`: at most 2 retries, only for failures that can pass |
| Writes (messages) | The outbox | `maxAttempts`, backoff and `nextAttemptAt`, saved across restarts |
| One-off calls (for example sign-in) | The call itself | `retries` option of `apiRequest`, default 0 |

The API client is where the pieces meet. It adds the token on **every attempt** (so a refreshed token is used on a retry), reports a refused token so Chapter 24’s refresh logic can run, and defaults to no retries of its own.

**mobile/lib/api/client.ts**

```
import { isUnauthorized } from '../net/errors';
import { requestJson, type JsonOptions } from '../net/fetchWithTimeout';
import { withRetry, type RetryOptions } from '../net/retry';

export interface ApiConfig {
  /** For example https://api.example.com/api/v1 (no trailing slash). */
  baseUrl: string;
  /** Your Chapter 24 token store. Called on every attempt so a refreshed token is
      used. */
  getToken: () => Promise<string | null>;
  /** Called after a 401, so Chapter 24's refresh or sign-out logic can run. */
  onUnauthorized?: () => void;
  fetchImpl?: typeof fetch;
}

let config: ApiConfig | null = null;

export function configureApi(next: ApiConfig): void {
  config = next;
}

export interface ApiRequestOptions<T> extends Omit<JsonOptions<T>, 'body' |
    'method' | 'headers'> {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  headers?: Record<string, string>;
  /** true only when repeating is safe: all GETs, and writes that carry an
      idempotency key. */
  idempotent?: boolean;
  /**
   * Retries inside this call. Default 0, on purpose: React Query (reads) and the
       outbox (writes)
   * already retry. Retrying in two layers multiplies the attempts.
   */
  retries?: number;
  retry?: Pick<RetryOptions, 'baseDelayMs' | 'maxDelayMs' | 'deadlineMs'>;
}

export async function apiRequest<T = unknown>(path: string, options:
    ApiRequestOptions<T> = {}): Promise<T> {
  if (!config) throw new Error('Call configureApi() before the first request.');
  const { baseUrl, getToken, onUnauthorized, fetchImpl } = config;
  const { method = 'GET', body, headers, idempotent = method === 'GET', retries =
      0, retry, ...rest } = options;

  return withRetry(
    async () => {
      const token = await getToken();
      try {
        return await requestJson<T>(`${baseUrl}${path}`, {
          ...rest,
          method,
          fetchImpl: rest.fetchImpl ?? fetchImpl,
          headers: {
            Accept: 'application/json',
            ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
            ...headers,
          },
          body: body === undefined ? undefined : JSON.stringify(body),
        });
      } catch (error) {
        if (isUnauthorized(error)) onUnauthorized?.();
        throw error;
      }
    },
    { ...retry, idempotent, retries, signal: rest.signal },
  );
}
```

> **Be a good citizen**
>
> Retries are load. Keep them few (two for reads), spaced (backoff and jitter), obedient (`Retry-After`) and limited to safe requests. Your own Chapter 17 rate limiter will answer a retry storm with 429s, and this client is built to listen.


## Doing Less Over the Wire

The fastest request is the one you do not make, and the cheapest byte is the one you do not send. On a slow or paid connection, sending less beats retrying better.

| **Technique** | **Effect** | **How** |
|---|---|---|
| **Fetch only what the screen shows** | Smaller responses, faster first paint | Cursor pagination from Chapters 8 and 12. Load the newest page of messages, more on scroll |
| **Do not refetch what is fresh** | No request at all | `staleTime` (25.4). Never set it to 0 everywhere |
| **Refetch when the user returns, not on a timer** | Fresh data exactly when it is seen | `focusManager` is wired to the app state in `setupManagers.ts` |
| **Do not poll** | No battery drain, no wasted requests | Use the WebSocket (Chapter 14) and push notifications (Chapter 24) |
| **Debounce typing** | One request per pause, not per key | Wait about 300 ms after the last keystroke before searching |
| **Right-sized images** | Often the biggest saving of all | Ask the server for thumbnails if you generate them (Chapter 16); cache with `expo-image` |
| **Compression** | JSON shrinks a lot | Usually switched on at the reverse proxy. Check that responses carry a `content-encoding` header |
| **Hold back on poor or metered links** | Respects the user’s data and patience | `shouldDeferLargeTransfers` (25.3) for uploads and image prefetching |

Images deserve a closer look because they are usually the heaviest thing on a screen. `expo-image` keeps a disk and memory cache, shows a placeholder while loading and fades the picture in. In lists, pass `recyclingKey` so a recycled row does not briefly show the previous row’s picture.

**typescript (pattern)**

```typescript
import { Image } from 'expo-image';

<Image
  source={{ uri: thumbnailUrl }}           // a small version, not the 4000-pixel
      original
  style={{ width: 48, height: 48, borderRadius: 24 }}
  cachePolicy="memory-disk"
  placeholder={{ blurhash }}               // or a colour or a local image
  transition={150}
  recyclingKey={item.id}                   // inside FlashList or FlatList rows
  accessibilityLabel={`Avatar of ${item.name}`}
/>
```

And a pattern for letting the connection quality decide, using the hook from Chapter 25:

**typescript (pattern)**

```typescript
const { deferLargeTransfers } = useConnectivity();

// Wi-Fi only for big uploads when the connection is poor or metered
const canUploadNow = !deferLargeTransfers;
```


## Streaming Replies on a Flaky Connection

AI replies reach the phone as a stream over a WebSocket (Chapters 14, 21 and 24), so the user sees words appear as the model writes them. A phone breaks that connection constantly: it switches networks, enters a tunnel, or goes to the background, where the operating system soon closes its sockets. The socket must therefore be treated as a convenience that can vanish at any moment, with the REST API as the truth.

| **Rule** | **Why** |
|---|---|
| **Reconnect with backoff and jitter** | The same politeness as for requests: a thousand phones must not reconnect in one second |
| **Do not retry while offline** | It wastes battery. Wait for the network, then reconnect at once |
| **Reset the backoff only after a connection has been stable** | A flapping connection that opens and drops would otherwise retry quickly forever |
| **Give up after a number of failures, and say so** | Then offer a manual “Reconnect”, and try again when the user returns to the app |
| **Ignore events from a socket you replaced** | A late event from an old socket must not touch the new state |
| **After reconnecting, fetch what you missed** | The complete reply is stored on the server. One refetch heals the screen |

The policy counts failed attempts and hands out the next jittered delay, or `null` when it is time to give up. The file is long, so the listings show the parts that carry the rules; the whole file is in the book’s GitHub repository.

**mobile/lib/net/reconnect.ts (policy and socket type)**

```
import { backoffDelay, type BackoffOptions } from './retry';

export interface ReconnectOptions extends BackoffOptions {
  /** Give up after this many failed attempts in a row (default 10). */
  maxAttempts?: number;
}

/** Counts failed attempts and hands out the next jittered delay, or null when it
    is time to give up. */
export class ReconnectPolicy {
  private attempts = 0;
  constructor(private readonly options: ReconnectOptions = {}) {}

  nextDelay(): number | null {
    if (this.attempts >= (this.options.maxAttempts ?? 10)) return null;
    return backoffDelay(this.attempts++, this.options);
  }
  reset(): void {
    this.attempts = 0;
  }
  get attemptCount(): number {
    return this.attempts;
  }
}

export type SocketStatus = 'connecting' | 'open' | 'reconnecting' | 'offline' |
    'closed' | 'gave-up';

/**
 * The small part of the WebSocket API we use, so tests can pass a fake. The
     handler parameters are
 * `any` on purpose: it lets the real WebSocket (whose events are MessageEvent and
     Event) and a
 * simple fake both fit without casts.
 */
export interface SocketLike {
  onopen: ((event: any) => void) | null;
  onclose: ((event: any) => void) | null;
  onerror: ((event: any) => void) | null;
  onmessage: ((event: any) => void) | null;
  send(data: string): void;
  close(code?: number): void;
}
```

**mobile/lib/net/reconnect.ts (ReconnectingSocket, the key methods)**

```
  /** Call with NetInfo's verdict (see isOnline). */
  setOnline(online: boolean): void {
    if (online === this.online) return;
    this.online = online;
    if (!this.wantOpen) return;
    if (!online) {
      this.clearTimers();
      this.dropSocket();
      this.setStatus('offline');
    } else {
      this.policy.reset();
      this.connect();
    }
  }

  send(data: string): boolean {
    if (this.status !== 'open' || !this.socket) return false;
    this.socket.send(data);
    return true;
  }

  private connect(): void {
    this.clearTimers();
    this.dropSocket();
    if (!this.wantOpen) return;
    if (!this.online) return this.setStatus('offline');

    this.setStatus(this.policy.attemptCount === 0 ? 'connecting' : 'reconnecting');
    const socket = this.options.createSocket();
    this.socket = socket;

    socket.onopen = () => {
      if (socket !== this.socket) return;
      this.setStatus('open');
      this.stableTimer = this.setT(() => this.policy.reset(), this.stableAfterMs);
    };
    socket.onmessage = (event) => {
      if (socket === this.socket) this.options.onMessage(event.data);
    };
    socket.onclose = () => {
      if (socket !== this.socket) return;
      this.socket = null;
      if (this.stableTimer) this.clearT(this.stableTimer);
      this.stableTimer = null;
      this.scheduleReconnect();
    };
    socket.onerror = () => {
      // A close event always follows; the reconnect is scheduled there.
    };
  }

  private scheduleReconnect(): void {
    if (!this.wantOpen || !this.online) return;
    const delay = this.policy.nextDelay();
    if (delay === null) return this.setStatus('gave-up');
    this.setStatus('reconnecting');
    this.retryTimer = this.setT(() => this.connect(), delay);
  }

  // ... dropSocket, clearTimers and setStatus are in the code download ...
}
```

The class takes a `createSocket` function and never creates a WebSocket itself, so the tests can hand it a fake that opens, drops and receives on command, with a clock the test advances by hand.

**mobile/__tests__/reconnect.test.ts (excerpt)**

```
it('forgets earlier failures only after the connection has stayed up for a while',
    () => {
  socket.start();
  sockets[0].drop();
  timers.fireNext(); // attempt 0
  sockets[1].open();
  timers.fireNext(); // the "stable for 10 s" timer: attempts reset
  sockets[1].drop();
  assert.equal(timers.fireNext(), 250); // starts from the beginning again

  sockets[2].open();
  sockets[2].drop(); // flapping: dropped before it counted as stable
  assert.equal(timers.fireNext(), 500); // the backoff kept growing
});

it('pauses while offline and reconnects at once when the network returns', () => {
  socket.start();
  sockets[0].open();
  socket.setOnline(false);
  assert.equal(socket.status, 'offline');
  assert.equal(sockets[0].closed, true);
  assert.equal(timers.pending.size, 0);

  socket.setOnline(true);
  assert.equal(sockets.length, 2); // no waiting for a timer
  assert.equal(socket.status, 'connecting');
});
```

Wiring it to the real world takes one short file. Adapt the URL and message format to the WebSocket client you wrote in Chapter 24. Three things matter: the online state comes from the same `onlineManager` as everything else, a successful connection triggers a refetch of messages, and a socket that gave up is restarted when the user comes back to the app.

**mobile/lib/net/chatSocket.ts**

```
import { onlineManager } from '@tanstack/react-query';
import { AppState } from 'react-native';
import { queryClient } from '../query/client';
import { ReconnectingSocket, ReconnectPolicy, type SocketStatus } from
    './reconnect';

/**
 * Adapt to the WebSocket client you wrote in Chapter 24 (URL, token, message
     format).
 * What matters here: reconnect rules live in ONE place, and REST stays the source
     of truth.
 */
export function createChatSocket(options: {
  /** Called for every (re)connect, so it can add a fresh short-lived ticket or
      token each time. */
  url: () => string;
  onEvent: (event: unknown) => void;
  onStatus?: (status: SocketStatus) => void;
}) {
  const socket = new ReconnectingSocket({
    createSocket: () => new WebSocket(options.url()),
    onMessage: (data) => {
      try {
        options.onEvent(JSON.parse(String(data)));
      } catch {
        // ignore a frame we cannot read; never let one bad frame close the screen
      }
    },
    onStatus: (status) => {
      options.onStatus?.(status);
      // Whatever we missed while disconnected is on the server: fetch it.
      if (status === 'open') void queryClient.invalidateQueries({ queryKey:
          ['messages'] });
    },
    policy: new ReconnectPolicy({ maxAttempts: 8, maxDelayMs: 30_000 }),
  });

  const stopOnline = onlineManager.subscribe((online) => socket.setOnline(online));
  const appState = AppState.addEventListener('change', (status) => {
    if (status === 'active' && socket.status === 'gave-up') socket.start(); // the
        user came back: try again
  });

  return {
    start: () => socket.start(),
    send: (data: string) => socket.send(data),
    stop: () => {
      stopOnline();
      appState.remove();
      socket.stop();
    },
  };
}
```

> **Decide what a dropped connection does to the reply**
>
> When the phone disconnects in the middle of a reply, what should the server do with the generation? There are two sensible designs, and you should choose one on purpose in your Chapter 14 and 29 code. **Let it finish and store the result** (best for mobile: the phone reconnects, refetches and shows the complete reply), or **cancel it to save tokens** and let the user retry. Letting it run to the end costs tokens for replies nobody saw; cancelling costs patience. Either way, the phone must never be left showing half a sentence with no way forward: mark such a message as interrupted and offer “Try again”.


## Making It Feel Fast › Measure before you fix

Guessing is how apps get complicated for no gain. Measure first.

- **Test a release build on a modest phone.** Development mode adds checks that make the app slower than your users will ever see, and a flagship phone hides problems a three-year-old budget phone shows at once.
- **React Native DevTools** (press `j` in the Expo terminal) includes a profiler that shows which components rendered and why.
- **The performance monitor** in the developer menu shows UI and JavaScript frame rates while you scroll. A JavaScript frame rate far below 60 while the UI rate is fine points at too much JavaScript work.
- **Watch memory** in Android Studio’s profiler or Xcode’s Instruments while scrolling a long list with images. Memory that only grows is a leak (Chapter 25, group E).
| **Symptom** | **Likely cause** | **Fix** |
|---|---|---|
| Typing lags | The whole screen re-renders on every keystroke | Move the text state into the composer; memoise the list and its rows |
| Scrolling stutters | Heavy `renderItem`, big images, no recycling | FlashList, memoised rows, thumbnails, work done before render |
| Slow cold start | Too much at module scope, huge first screen | Lazy-load screens; keep the splash only until the cache is restored |
| Memory grows until the app closes | All history in state, big images, listeners never removed | Paginate, resize images, clean up effects |
| Every screen feels slow on poor networks | No saved data, long timeouts, polling | 25.4 |


## Catching Crashes in Production

Users do not send screenshots. A crash they hit on a Tuesday evening on a phone model you do not own is invisible unless the app reports it. A crash-reporting service collects the error, the app version, the device and the steps leading up to it, groups identical crashes together and tells you which ones affect the most people. Chapter 55 sets up monitoring end to end, including source maps, releases and alerts. This section covers the part that is specific to a chat app: **what must never leave the phone**.

| **Send** | **Never send** |
|---|---|
| The error and its stack trace | The text of any message or conversation title |
| App version, build, operating system, device model | Request and response bodies |
| An opaque user id (so you can count affected users) | E-mail, name, phone number, IP address |
| Breadcrumbs: screens visited, request URLs and status codes | Authorization headers, cookies, tokens, passwords |
| Whether the phone was offline, and the outbox size | Anything the user typed |

Chapter 17 (section 17.12) made the same point about server logs: a log that contains private data becomes a second copy of that data, with weaker protection. A crash report is a log that leaves the phone, so the same discipline applies. `scrubEvent` removes the sensitive parts, and Sentry is configured not to collect personal data by default.

**mobile/lib/crash/sentry.ts**

```
import * as Sentry from '@sentry/react-native';
import { scrubEvent } from './scrub';

/** Chapter 55 covers the full setup (source maps, releases, alerts). This is the
    privacy-safe core. */
export function initCrashReporting(): void {
  const dsn = process.env.EXPO_PUBLIC_SENTRY_DSN;
  if (!dsn) return; // development builds without a DSN simply report nothing
  Sentry.init({
    dsn,
    sendDefaultPii: false,
    tracesSampleRate: 0,
    beforeSend: (event) => scrubEvent(event),
  });
}

export const reportError = (error: unknown): void => {
  Sentry.captureException(error);
};
```

**mobile/lib/crash/scrub.ts**

```
/** The few parts of a crash report we clean before it leaves the phone. Sentry's
    event type satisfies this. */
export interface ScrubbableEvent {
  message?: string;
  user?: { email?: string; username?: string; ip_address?: string | null };
  request?: { data?: unknown; cookies?: unknown; headers?: Record<string, unknown>
      };
  breadcrumbs?: Array<{ message?: string; data?: Record<string, unknown> }>;
}

const BEARER = /Bearer\s+[A-Za-z0-9._~+/-]+=*/g;

export const scrubText = (text: string): string => text.replace(BEARER, 'Bearer
    [REDACTED]');

/**
 * Crash reports must not become a second copy of the user's conversations (Chapter
     17, section 17.12).
 * Keep the user's id, drop everything personal: request bodies, cookies, auth
     headers, e-mail, address.
 */
export function scrubEvent<T extends ScrubbableEvent>(event: T): T {
  if (event.message) event.message = scrubText(event.message);
  if (event.user) {
    delete event.user.email;
    delete event.user.username;
    delete event.user.ip_address;
  }
  if (event.request) {
    delete event.request.data;
    delete event.request.cookies;
    if (event.request.headers) {
      for (const name of Object.keys(event.request.headers)) {
        if (/^(authorization|cookie|set-cookie)$/i.test(name)) delete
            event.request.headers[name];
      }
    }
  }
  for (const crumb of event.breadcrumbs ?? []) {
    if (crumb.message) crumb.message = scrubText(crumb.message);
    if (crumb.data) delete crumb.data.request_body;
  }
  return event;
}
```

**mobile/__tests__/scrub.test.ts (excerpt)**

```
it('removes personal data and secrets, keeps what helps debugging', () => {
  const event = scrubEvent({
    message: 'Request failed with Authorization: Bearer abc.def-123',
    user: { id: 'u-42', email: 'ada@example.com', username: 'ada', ip_address:
        '1.2.3.4' },
    request: {
      url: 'https://api.example.com/api/v1/conversations/',
      data: { content: 'my private chat message' },
      cookies: 'sessionid=1',
      headers: { Authorization: 'Bearer abc', 'Content-Type': 'application/json' },
    },
    breadcrumbs: [{ message: 'sent Bearer zzz.yyy', data: { request_body: 'secret',
        status: 201 } }],
  });
  assert.equal(event.message, 'Request failed with Authorization: Bearer
      [REDACTED]');
  assert.deepEqual(event.user, { id: 'u-42' });
  assert.equal(event.request?.data, undefined);
  assert.equal(event.request?.cookies, undefined);
  assert.deepEqual(event.request?.headers, { 'Content-Type': 'application/json' });
  assert.equal(event.request?.url, 'https://api.example.com/api/v1/conversations/');
  assert.equal(event.breadcrumbs?.[0].message, 'sent Bearer [REDACTED]');
  assert.deepEqual(event.breadcrumbs?.[0].data, { status: 201 });
});
```

- **The DSN is not a secret.** It only lets a client send events, and Sentry designs it to be public. It can still be abused to flood your quota, which is why `beforeSend` and rate limits in the service matter. Keep it in `EXPO_PUBLIC_SENTRY_DSN`.
- **Triage on a rhythm.** Look at new and most frequent crashes weekly. Fix crashes that affect many users or happen at start-up first; a crash during launch is worth more than ten in a rarely used screen.
- **Tell the user something useful.** The error boundary fallback says that the rest of the app is fine and that their messages are safe, which is true because the outbox is on the phone.

## Testing Offline and Slow-Network Behaviour

A feature that was never tested offline does not work offline. The good news is that you do not need a laboratory: the phone, your emulator and a small amount of code are enough. There are two kinds of test. **Unit tests** cover the rules (retry timing, order, idempotency, merging); they run in seconds on your computer, which is what the 93 tests in this chapter do. **Device tests** cover what only a phone can show: that the banner appears, that the app restarts with its queue intact, that a slow connection feels acceptable.

| **How to simulate** | **What it gives you** | **Notes** |
|---|---|---|
| **Airplane mode** on a real phone | A clean “no network” | The simplest and most honest test |
| **Android emulator** extended controls (cellular) | Network type and signal strength, and switching connectivity off | Good for slow and flaky conditions without a physical phone |
| **iOS Network Link Conditioner** (developer settings on the phone) | Presets such as slow 3G and 100% loss | Needs developer mode; affects the whole phone, so switch it off afterwards |
| **A proxy that throttles** (such as Charles or mitmproxy) | Exact bandwidth and latency; can drop or delay selected requests | Good for “the response is lost” cases |
| **Stopping or slowing Django** | Connection refused, 5xx, long waits | Stop the server; add a temporary `time.sleep` to one view; lower a throttle to trigger 429 and `Retry-After` |
| **The chaos fetch** (below) | Latency, random failures and a software “offline” switch, in development only | Works the same on every device and is repeatable |


### A fetch that misbehaves on purpose

The chaos fetch wraps the real `fetch`. It adds random delay, fails a chosen share of requests (half as dropped connections, half as 503 with `Retry-After`) and can pretend the network is gone. Because the API client accepts a `fetchImpl`, you plug it in at one place. The tests show it also works together with the deadline code: a 5-second delay under a 30-millisecond deadline is reported as a timeout.

**mobile/lib/dev/chaosFetch.ts**

```
export interface ChaosOptions {
  base?: typeof fetch;
  /** Random delay range in ms added to every request. */
  latencyMs?: [min: number, max: number];
  /** 0 to 1. Half of the failures are dropped connections, half are 503 responses.
      */
  failureRate?: number;
  /** true, or a function, to behave as if the phone had no network. */
  offline?: boolean | (() => boolean);
  random?: () => number;
  delay?: (ms: number, signal?: AbortSignal | null) => Promise<void>;
}

const abortError = () => Object.assign(new Error('Aborted'), { name: 'AbortError'
    });

const abortableDelay = (ms: number, signal?: AbortSignal | null) =>
  new Promise<void>((resolve, reject) => {
    if (signal?.aborted) return reject(abortError());
    const onAbort = () => {
      clearTimeout(timer);
      reject(abortError());
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    signal?.addEventListener('abort', onAbort, { once: true });
  });

/** A fetch that misbehaves on purpose. Wrap your real fetch with it in development
    only. */
export function createChaosFetch({
  base = fetch,
  latencyMs = [0, 0],
  failureRate = 0,
  offline = false,
  random = Math.random,
  delay = abortableDelay,
}: ChaosOptions = {}): typeof fetch {
  const isOffline = typeof offline === 'function' ? offline : () => offline;

  return async (input, init) => {
    const signal = init?.signal;
    const [min, max] = latencyMs;
    await delay(min + Math.floor(random() * (max - min)), signal);

    if (isOffline()) throw new TypeError('Network request failed');
    const roll = random();
    if (roll < failureRate / 2) throw new TypeError('Network request failed');
    if (roll < failureRate) return new Response('Service Unavailable', { status:
        503, headers: { 'Retry-After': '1' } });
    return base(input, init);
  };
}
```

**typescript (pattern, development only)**

```typescript
// lib/dev/devNetwork.ts
import { onlineManager } from '@tanstack/react-query';
import { createChaosFetch } from './chaosFetch';

export const devNetwork = { offline: false };

export const chaosFetch = createChaosFetch({
  latencyMs: [300, 2500],               // every request takes 0.3 to 2.5 seconds
  failureRate: 0.2,                     // one in five fails
  offline: () => devNetwork.offline,    // flip from a hidden developer screen
});

export function setDevOffline(offline: boolean) {
  devNetwork.offline = offline;
  onlineManager.setOnline(!offline);    // so the banner and paused queries follow
}

// in the root layout:
configureApi({ baseUrl: API_URL, getToken, fetchImpl: __DEV__ ? chaosFetch :
    undefined });
```

> **Guard development tools with __DEV__**
>
> A chaos fetch that reaches a production build makes real users’ requests fail on purpose. `__DEV__` is `false` in release builds, so the pattern above leaves `fetchImpl` unset there. Check it in your first release build.


### The scenarios to run before every release

| **Scenario** | **Steps** | **Expected** |
|---|---|---|
| Cold start offline | Open the app in airplane mode after using it online | Saved conversations appear at once; banner after about 1.5 s; no spinner that never ends |
| Write offline | Send two messages offline | Both show “Sending...” in order; the text box clears; nothing is lost |
| Kill and relaunch | With messages waiting, force-close the app and open it again | Both messages are still there, still waiting |
| Reconnect | Switch the network back on | Both send, in order, once; the server has exactly two new rows |
| Lost response | Use the chaos fetch or a proxy so the answer is lost after the server stored it | Still exactly one message on the server |
| Slow network | Throttle to slow 3G and open a conversation | Saved data first; a clear status; no freeze |
| Rejected message | Send text longer than the server allows | Marked “Not sent” with a reason, and “Try again” and “Delete” work |
| Token expired mid-queue | Let the access token expire with messages waiting | Nothing is discarded; after signing in again the queue is sent |
| Two users | Sign out and sign in as someone else, offline | No trace of the first user: cache, queue and drafts are gone |
| Server down | Stop Django | Retries back off and stop; the user gets a calm message; the app does not hammer the server |
| A broken screen | Make one screen throw on purpose | The fallback appears for that screen; the rest of the app works |

Chapter 39 covers testing strategy for React Native in depth, including component tests and end-to-end tests that can automate several of these scenarios. Until then, this table is your manual release checklist.
