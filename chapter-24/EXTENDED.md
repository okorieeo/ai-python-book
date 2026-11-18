# Chapter 24 — Building the Mobile App: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## What We Are Building › What we assume from Chapter 14

The live inbox uses the WebSocket server you built in Chapter 14. Three details of that design matter to the phone, and they are isolated in two small places (`getUrl` in `useInbox.ts` and the message check `isItem`), so they are easy to adjust if your code differs.

| **Assumption** | **What the app does** |
|---|---|
| A logged-in client can call **POST /ws/ticket** and receive `{"ticket": "..."}` that is valid for a few seconds and works once | Asks for a new ticket before every connection attempt |
| The socket is at **/ws/notifications/?ticket=...** and closes with code **4403** when the ticket is refused | Treats 4403 as final and stops retrying |
| Messages are JSON like `{"type": "notification", "id": "...", "title": "...", "body": "..."}` | Ignores anything that does not match that shape |


## Secure Token Storage › Tests

**mobile/__tests__/tokenStore.test.ts (excerpt)**

```
  it("keeps the access token in memory and the refresh token in storage", async () => {
    const storage = memoryStorage();
    const store = createTokenStore(storage);
    await store.setTokens({ access: "A1", refresh: "R1" });
    expect(store.getAccess()).toBe("A1");
    expect(storage.data).toEqual({ [REFRESH_KEY]: "R1" }); // the access token is NOT here
  });

  it("survives an app restart with the refresh token only", async () => {
    const storage = memoryStorage();
    await createTokenStore(storage).setTokens({ access: "A1", refresh: "R1" });
    const afterRestart = createTokenStore(storage); // a new process, same Keychain
    expect(afterRestart.getAccess()).toBeNull();
    expect(await afterRestart.getRefresh()).toBe("R1");
  });
```

The first test proves the rule that matters: after `setTokens`, the storage holds the refresh token and nothing else. The second simulates a restart by creating a second store on the same storage.


## The API Client › Tests

The tests use a fake `fetch` that answers from a function and remembers every call, and a fake storage. The most important ones:

**mobile/__tests__/client.test.ts (excerpt)**

```
// A server that accepts only the access token "A2" and rotates refresh tokens.
const rotatingServer: Handler = (url, init) => {
  if (url.endsWith("/auth/token/refresh")) {
    return json(200, { access: "A2", refresh: "R2" });
  }
  const auth = (init.headers as Record<string, string>).Authorization;
  return auth === "Bearer A2"
    ? json(200, { ok: true })
    : json(401, { error: { code: "token_expired", message: "The token is expired." } });
};

it("refreshes on 401, retries once and keeps the ROTATED refresh token", async () => {
  const { client, store, storage, calls, onSignedOut } = await setup(rotatingServer);
  expect(await client.get("/me")).toEqual({ ok: true });
  expect(calls.map((c) => c.url.split("/api/v1")[1])).toEqual([
    "/me", "/auth/token/refresh", "/me",
  ]);
  expect(header(calls[2], "Authorization")).toBe("Bearer A2");
  expect(storage.data[REFRESH_KEY]).toBe("R2");
  expect(onSignedOut).not.toHaveBeenCalled();
});

it("three parallel 401s cause exactly ONE refresh", async () => {
  const { client, calls } = await setup(rotatingServer);
  await Promise.all([client.get("/a"), client.get("/b"), client.get("/c")]);
  expect(calls.filter((c) => c.url.endsWith("/auth/token/refresh"))).toHaveLength(1);
});

it("does NOT sign out when the phone is offline during the refresh", async () => {
  // ...the refresh call throws "Network request failed"
  await expect(client.get("/me")).rejects.toBeInstanceOf(NetworkError);
  expect(onSignedOut).not.toHaveBeenCalled();
  expect(storage.data[REFRESH_KEY]).toBe("R1"); // still signed in
});
```

There are 22 tests for the token store and the client in total. They also cover the error envelope, the HTML error page, a 204, the multipart boundary, a timeout, a server error during refresh, a refused new token, sign-in with `auth: false`, and the four ways a session can be restored at launch. To prove that tests like these are worth having, break the code on purpose: remove the shared `refreshing` promise, or make `isSessionOver` accept every error. Each change turns a specific test red.


## Consuming the API: Lists, Pagination and Signed Links › Opening a private file: the redirect trap

Chapter 16’s `GET /documents/{id}/download` answers **302** with a signed URL pointing at the bucket. A browser follows that redirect without trouble. A phone’s HTTP stack follows it too, and it may carry your `Authorization: Bearer` header along. S3 and R2 refuse a request that has two kinds of credentials (the header and the signature in the URL), so the download fails with a confusing 400 that appears only on the phone.

The fix is to stop redirecting for mobile clients. We add one endpoint that returns the signed URL **as JSON**. The app then opens the URL by itself, with no headers:

**backend/documents/views.py (add)**

```
# documents/views.py (add)
class DocumentLink(APIView):
    """Give the client a signed URL as JSON, instead of redirecting to it.

    A phone's HTTP client follows our 302 and may send our Authorization header to the
    bucket too. S3 refuses a request that carries two kinds of credentials. So the app
    asks for the link, and then opens it by itself, with no headers.
    """

    def get(self, request, public_id):
        doc = generics.get_object_or_404(request.user.documents, public_id=public_id)
        storage = store.get_storage()
        inline = request.query_params.get("inline") == "1" and (
            doc.content_type.startswith("image/") or doc.content_type == "application/pdf"
        )
        if store.is_local(storage):  # development: the file is served from /media/
            url = request.build_absolute_uri(storage.url(doc.storage_key))
            expires = None
        else:  # production: a link that stops working in 5 minutes
            params = {} if inline else {"ResponseContentDisposition": "attachment"}
            url = storage.url(doc.storage_key, parameters=params)
            expires = 300
        return Response(
            {
                "url": url,
                "expires_in": expires,
                "content_type": doc.content_type,
                "filename": doc.filename,
            }
        )
```

**backend/documents/urls.py (add one line)**

```
    path("documents/<uuid:public_id>/link", views.DocumentLink.as_view()),
```

The permission check is unchanged: the document is looked up through `request.user.documents`, so a stranger gets 404 before any URL exists. In development, where files live in `MEDIA_ROOT`, the URL points at the `/media/` route that Django serves when `DEBUG` is on. In production it is a signed URL that dies in five minutes. `?inline=1` leaves out the “download as attachment” header, but only for images and PDFs, types we know are safe to display. Everything else is always an attachment.

On the documents screen, a tap calls `api.documentLink(id, true)` and passes the answer to `Linking.openURL`, which hands the link to the system browser or the PDF viewer. A long press asks for confirmation (`Alert.alert`) and then calls `DELETE /documents/{id}`. The new tests (in the same style as Chapter 16) check that the owner gets a URL, a stranger gets 404, the S3 link carries `X-Amz-Signature` and `X-Amz-Expires=300`, and that `inline=1` drops the attachment header.

**documents/tests.py (add)**

```
class LinkTests(FileTestCase):
    def test_link_returns_a_url_for_the_owner_only(self):
        doc_id = self.post_file().data["id"]
        r = self.client.get(f"{API}/documents/{doc_id}/link")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["url"].startswith("http://testserver/media/documents/"))
        other = User.objects.create_user(
            "bo@example.com", "correct-horse-battery-staple", name="Bo"
        )
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get(f"{API}/documents/{doc_id}/link").status_code, 404)
```


## Real-Time Updates with WebSockets › The app lifecycle

When the person switches to another app, iOS and Android suspend yours, and the socket dies. A connection that you believe is open but is dead is worse than no connection, because messages are lost silently. The hook therefore stops the socket when the app goes to the background and starts it when the app becomes active again, and calls `reconnectNow()` to skip any back-off that was running.

**mobile/src/realtime/useInbox.ts**

```
import { useEffect, useRef, useState } from "react";
import { AppState } from "react-native";

import { api } from "../api";
import { WS_URL } from "../config";
import { createSocket, type SocketStatus } from "./socket";

export interface InboxItem {
  id: string;
  title: string;
  body: string;
  created_at: string;
}

const isItem = (m: any): m is InboxItem & { type: "notification" } =>
  m && m.type === "notification" && typeof m.id === "string" && typeof m.title === "string";

export function useInbox() {
  const [items, setItems] = useState<InboxItem[]>([]);
  const [status, setStatus] = useState<SocketStatus>("idle");
  const socketRef = useRef<ReturnType<typeof createSocket> | null>(null);

  useEffect(() => {
    const socket = createSocket({
      // A fresh one-use ticket for every attempt (Chapter 14).
      getUrl: async () => {
        const { ticket } = await api.socketTicket();
        return `${WS_URL}/ws/notifications/?ticket=${encodeURIComponent(ticket)}`;
      },
      onStatus: setStatus,
      onMessage: (message) => {
        if (!isItem(message)) return;
        // keep the newest 50, and ignore a repeat of an id we already have
        setItems((old) =>
          old.some((i) => i.id === message.id) ? old : [message, ...old].slice(0, 50),
        );
      },
    });
    socketRef.current = socket;
    socket.start();

    // Phones kill sockets of sleeping apps. Close when hidden, reconnect when shown.
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active") {
        socket.start();
        socket.reconnectNow();
      } else {
        socket.stop();
      }
    });
    return () => {
      sub.remove();
      socket.stop();
    };
  }, []);

  return { items, status };
}
```

The Inbox screen shows `status` as a small dot: **Live**, **Reconnecting…**, **Offline**. It is a few lines of interface and it prevents a large class of support questions, because the person can see whether the screen is current. Notice also the duplicate check in `onMessage`: a message with an id we already hold is ignored, which makes reconnection safe even if the server replays the last event.

> **The inbox is not a database**
>
> The list lives in memory and keeps the newest 50. When the app is closed it is gone, and so are messages that arrived while it was closed. That is correct for a first version: the truth is on the server, and push notifications (the next section) cover the closed-app case. A history endpoint, so that the Inbox loads what it missed, is Exercise 6.


## Real-Time Updates with WebSockets › Tests

The socket tests use a `FakeSocket` that plays the part of the server (`open()`, `say()`, `drop(code)`) and fake timers that record each delay instead of waiting:

**mobile/__tests__/socket.test.ts (excerpt)**

```
it("reconnects with growing delays, and starts over after a good connection", async () => {
  const { socket, timers, last } = setup();
  socket.start();
  await flush();
  last().drop(); // attempt 0 never opened
  timers.fireNext();
  await flush();
  last().drop(); // attempt 1 never opened
  timers.fireNext();
  await flush();
  last().open(); // finally connected
  last().drop(); // and lost again
  expect(timers.delays).toEqual([1000, 2000, 1000]); // 1000 again: the counter was reset
});

it("gives up on a forbidden close code instead of retrying forever", async () => {
  const { socket, timers, last } = setup();
  socket.start();
  await flush();
  last().open();
  last().drop(4403);
  expect(socket.status).toBe("stopped");
  expect(timers.pending).toHaveLength(0);
});
```

The ten socket tests also cover message parsing, a fresh ticket per attempt, a failing ticket request, `stop()`, late events from a replaced socket, and `reconnectNow()`.


## Push Notifications › The server: the `devices` app

**devices/models.py**

```
import uuid

from django.conf import settings
from django.db import models

class PushDevice(models.Model):
    """One phone (really: one app install) that may receive push notifications."""

    class Platform(models.TextChoices):
        IOS = "ios"
        ANDROID = "android"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_devices",
    )
    # UNIQUE across all users: a token belongs to one phone, and a phone has one
    # signed-in account at a time. If Bo signs in on Ada's old phone, the row moves.
    token = models.CharField(max_length=200, unique=True)
    platform = models.CharField(max_length=10, choices=Platform)
    device_name = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "push_devices"
        indexes = [
            models.Index(fields=["user", "is_active"], name="idx_push_devices_user")
        ]
```

**devices/serializers.py**

```
import re

from rest_framework import serializers

from .models import PushDevice

# ExponentPushToken[xxxx] is the older spelling, ExpoPushToken[xxxx] the newer one.
TOKEN_PATTERN = re.compile(r"^(Expo|Exponent)PushToken\[[A-Za-z0-9_-]+\]$")

class DeviceSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = PushDevice
        fields = ["id", "token", "platform", "device_name", "created_at"]
        # The token is accepted but never echoed back: it is a delivery address.
        # validators=[] removes the automatic "must be unique" check: registering the
        # same token twice is allowed, and is an update, not an error.
        extra_kwargs = {"token": {"write_only": True, "validators": []}}

    def validate_token(self, value):
        if not TOKEN_PATTERN.match(value):
            raise serializers.ValidationError("This is not an Expo push token.")
        return value
```

**devices/views.py**

```
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from .models import PushDevice
from .serializers import DeviceSerializer

class DeviceCreate(generics.GenericAPIView):
    serializer_class = DeviceSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "devices"
    pagination_class = None

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        # An upsert keyed on the token. Safe to call at every app launch, and it
        # moves the token to the current account if the phone changed hands.
        device, created = PushDevice.objects.update_or_create(
            token=data["token"],
            defaults={
                "user": request.user,
                "platform": data["platform"],
                "device_name": data.get("device_name", ""),
                "is_active": True,
            },
        )
        return Response(
            DeviceSerializer(device).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

class DeviceDetail(generics.DestroyAPIView):
    lookup_field = "public_id"

    def get_queryset(self):
        return self.request.user.push_devices.all()  # someone else's id is a 404
```

The create endpoint is an **upsert**: `update_or_create(token=...)` creates the row the first time, updates it afterwards and, because the lookup is by token alone, moves it to the current user when the phone changed hands. The app calls it on every launch, which is harmless and keeps `last_seen_at` honest. It answers 201 when it created the row and 200 otherwise, the same convention as Chapter 16’s uploads. Deleting uses the device’s public id, and `get_queryset` is limited to the caller’s own devices, so someone else’s id is a 404 (Chapter 8’s rule: do not reveal what exists).

The validator on `token` is deliberately strict. A token is later placed in a request to a third party, so we accept only the exact format. Because `token` is `unique=True`, DRF would add its own “must be unique” check, which would turn the second registration into an error; `"validators": []` removes it. Add the route and the settings:

**config/settings.py and config/urls.py (changes)**

```
INSTALLED_APPS += ["devices"]

REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["devices"] = "30/hour"

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
# Optional: only needed if you enable "enhanced push security" in your Expo account.
EXPO_PUSH_ACCESS_TOKEN = os.environ.get("EXPO_PUSH_ACCESS_TOKEN", "")

# config/urls.py
    path("api/v1/", include("devices.urls")),
```


## Push Notifications › The server’s tests

The tests replace `requests.post` with a mock, in the style of Chapter 16’s webhook tests, so no network is needed:

**devices/tests.py (excerpt)**

```
    def test_a_token_moves_to_the_account_that_signs_in_on_the_phone(self):
        self.register()
        bo = make_user("bo@example.com")
        self.client.force_authenticate(bo)
        self.assertEqual(self.register().status_code, 200)
        self.assertEqual(PushDevice.objects.get().user, bo)  # Ada no longer gets Bo's pushes

    def test_messages_go_out_in_batches_of_100(self):
        for n in range(250):
            self.add_device(n)
        with mock.patch(
            "requests.post",
            side_effect=lambda url, json, **kw: ok_response([{"status": "ok"}] * len(json)),
        ) as post:
            result = send_push(self.user, "Hi", "There")
        self.assertEqual([len(c.kwargs["json"]) for c in post.call_args_list], [100, 100, 50])
        self.assertEqual(result["sent"], 250)

    def test_a_device_that_is_not_registered_is_switched_off(self):
        self.add_device(1)
        self.add_device(2)
        tickets = [
            {"status": "ok", "id": "1"},
            {"status": "error", "message": "gone", "details": {"error": "DeviceNotRegistered"}},
        ]
        with mock.patch("requests.post", return_value=ok_response(tickets)):
            result = send_push(self.user, "Hi", "There")
        self.assertEqual(result, {"sent": 1, "deactivated": 1})
        self.assertEqual(self.user.push_devices.filter(is_active=True).count(), 1)
```

There are 15 tests in all: registration, repeat registration, malformed tokens and platforms, a token changing hands, reactivation, ownership of deletes, login, throttling, one request per send, no devices, batching, `DeviceNotRegistered`, a network failure, an oversized payload and the optional access token.


## Push Notifications › The app: permission, channel, token

On the phone, getting a token takes four steps, in an order that matters.

- **Create the Android channel first.** Since Android 8 every notification belongs to a *channel* the user can configure, and since Android 13 the system permission dialog does not appear until at least one channel exists. Our channel is called `default`, and the server names it in every message (`"channelId": "default"`).
- **Check the permission, and ask only when the person has chosen to enable notifications.** Do **not** ask at launch. A dialog before the person has seen any value is refused far more often, and on iOS you get only one chance: after “Don’t Allow” the system never shows the dialog again.
- **Get the Expo token for your project** with `getExpoPushTokenAsync({ projectId })`. The project id is the one `eas init` wrote.
- **Register the token with the server.** If anything fails (offline, no Google Play services, missing credentials), report it; never crash.
**mobile/src/push/pushActions.ts**

```
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

import { deviceRegistrar } from "../api";
import { EAS_PROJECT_ID } from "../config";

export type PushResult =
  | { kind: "ok"; token: string }
  | { kind: "denied"; canAskAgain: boolean }
  | { kind: "unavailable"; reason: string };

// How a notification looks while the app is OPEN. Call once, at startup.
export function installForegroundHandler() {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: true, // on Android, false would hide the banner as well
      shouldSetBadge: false,
    }),
  });
}

const allowed = (p: Notifications.NotificationPermissionsStatus) =>
  p.granted || p.ios?.status === Notifications.IosAuthorizationStatus.PROVISIONAL;

/**
 * askUser=false  look only (used silently at launch)
 * askUser=true   show the system dialog if the system still allows it
 */
export async function getPushToken(askUser: boolean): Promise<PushResult> {
  // Android 13+ shows its permission dialog only once a channel exists, so this comes first.
  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("default", {
      name: "General",
      importance: Notifications.AndroidImportance.HIGH,
    });
  }

  let permission = await Notifications.getPermissionsAsync();
  if (!allowed(permission) && permission.canAskAgain && askUser) {
    permission = await Notifications.requestPermissionsAsync();
  }
  if (!allowed(permission)) return { kind: "denied", canAskAgain: permission.canAskAgain };

  if (!EAS_PROJECT_ID) {
    return { kind: "unavailable", reason: "No EAS project id. Run `eas init` and rebuild." };
  }
  try {
    const token = await Notifications.getExpoPushTokenAsync({ projectId: EAS_PROJECT_ID });
    return { kind: "ok", token: token.data };
  } catch (e) {
    // Offline, no Google Play services, missing credentials: report it, do not crash.
    return { kind: "unavailable", reason: e instanceof Error ? e.message : String(e) };
  }
}

/** Get a token (asking if allowed) and tell the server about it. */
export async function enablePush(askUser: boolean): Promise<PushResult> {
  const result = await getPushToken(askUser);
  if (result.kind === "ok") {
    const platform = Platform.OS === "ios" ? "ios" : "android";
    await deviceRegistrar.register(result.token, platform, Device.modelName ?? Platform.OS);
  }
  return result;
}

export async function disablePush() {
  await deviceRegistrar.unregister();
}
```

> **On Android, shouldPlaySound: false also hides the banner**
>
> In the foreground handler, Expo’s documentation notes that on Android, `shouldPlaySound: false` stops the drop-down banner from appearing at all, whatever the priority. We therefore leave the sound on. If your app also receives each message through the WebSocket, a foreground push duplicates it; the inbox ignores repeated ids, and Exercise 8 suppresses the banner as well.

`getPushToken(false)` only *looks*: it never shows a dialog. `getPushToken(true)` may show it. The Profile screen calls `enablePush(true)` when the person taps “Turn on notifications”, which is the moment the system dialog should appear, because the person has just asked for it. The registrar remembers the id the server returned, so that sign-out can delete exactly this device:

**mobile/src/push/registrar.ts**

```
import { ApiError } from "../api/errors";
import type { Endpoints } from "../api/endpoints";
import type { KeyValueStorage } from "../auth/tokenStore";

export const DEVICE_KEY = "push.device_id";

/** Tells the server "send pushes for this account to this token", and takes it back. */
export function createDeviceRegistrar(deps: {
  storage: KeyValueStorage;
  api: Pick<Endpoints, "registerDevice" | "unregisterDevice">;
}) {
  const { storage, api } = deps;

  return {
    // Safe to call on every launch: the server treats it as an upsert.
    async register(token: string, platform: "ios" | "android", deviceName: string) {
      const device = await api.registerDevice(token, platform, deviceName);
      await storage.setItem(DEVICE_KEY, device.id);
      return device.id;
    },

    async isRegistered() {
      return (await storage.getItem(DEVICE_KEY)) !== null;
    },

    // Called on logout. A 404 means the server already forgot it: that is fine.
    async unregister() {
      const id = await storage.getItem(DEVICE_KEY);
      if (!id) return;
      try {
        await api.unregisterDevice(id);
      } catch (e) {
        if (!(e instanceof ApiError && e.status === 404)) throw e;
      }
      await storage.removeItem(DEVICE_KEY);
    },
  };
}

export type DeviceRegistrar = ReturnType<typeof createDeviceRegistrar>;
```

A 404 on unregister means the server already forgot the device, so it counts as success; any other failure is raised, because a phone that keeps receiving a former user’s notifications is a privacy bug.


## Camera, Image Picker and Permissions › Three states, not two

Beginners treat a permission as granted or not granted. On a phone it has three states, and each needs a different screen:

| **State** | **Meaning** | **What to do** |
|---|---|---|
| **granted** | The person said yes | Go ahead |
| **denied** | The person said no, but the system will ask again | Explain why you need it, in a moment that makes sense, then ask again |
| **blocked** | The system will not show its dialog again (iOS after the first “Don’t Allow”; Android after the second, or “Don’t ask again”) | Calling `request` does nothing and shows nothing. Send the person to Settings with `Linking.openSettings()` |

The most common permission bug in the wild is calling the request function on a blocked permission and having the button do *nothing*. `ensurePermission` turns the three states into one function the screens can use:

**mobile/src/media/permissions.ts**

```
// Every permission has three states, and each needs a different screen:
//   granted  go ahead
//   denied   ask again, in a moment that makes sense, with a reason
//   blocked  the system will not show its dialog again: send the person to Settings

export interface PermissionLike {
  granted: boolean;
  canAskAgain: boolean;
}

export type PermissionOutcome = "granted" | "denied" | "blocked";

export async function ensurePermission(
  get: () => Promise<PermissionLike>,
  request: () => Promise<PermissionLike>,
): Promise<PermissionOutcome> {
  const current = await get();
  if (current.granted) return "granted";
  // Android shows its dialog twice at most; after that request() returns at once
  // with nothing on screen. Do not pretend to ask: say it plainly.
  if (!current.canAskAgain) return "blocked";
  const answer = await request();
  if (answer.granted) return "granted";
  return answer.canAskAgain ? "denied" : "blocked";
}
```

**mobile/__tests__/media.test.ts (excerpt)**

```
it("reports blocked, without asking, when the system will not show its dialog", async () => {
  const request = jest.fn();
  expect(await ensurePermission(async () => never, request)).toBe("blocked");
  expect(request).not.toHaveBeenCalled();
});

it("reports blocked when the person chooses Don't ask again", async () => {
  expect(await ensurePermission(async () => no, async () => never)).toBe("blocked");
});
```


## Camera, Image Picker and Permissions › The image picker: camera and library

`expo-image-picker` opens the system’s own screens, which is the best default: they are familiar, accessible and maintained by Apple and Google. There is an important asymmetry between its two entry points. The **library** uses the system photo picker, which shows only the photos the person selects, so it needs **no permission at all**. The **camera** needs the camera permission, and we ask for it with `ensurePermission`, at the moment the person taps “Take a photo”.

**mobile/src/media/pickImage.ts**

```
import * as ImagePicker from "expo-image-picker";

import { toFormData, validateAsset, type PickedAsset } from "./mediaRules";
import { ensurePermission, type PermissionOutcome } from "./permissions";

export type PickResult =
  | { kind: "picked"; asset: PickedAsset; form: FormData }
  | { kind: "cancelled" }
  | { kind: "invalid"; message: string }
  | { kind: "permission"; outcome: Exclude<PermissionOutcome, "granted"> };

function finish(result: ImagePicker.ImagePickerResult): PickResult {
  if (result.canceled || result.assets.length === 0) return { kind: "cancelled" };
  const asset = result.assets[0];
  const verdict = validateAsset(asset);
  if (!verdict.ok) return { kind: "invalid", message: verdict.message };
  return { kind: "picked", asset, form: toFormData(asset) };
}

// quality below 1 makes the picker re-encode the photo as a smaller JPEG.
const options = { mediaTypes: ["images" as const], quality: 0.8 };

export async function choosePhoto(square = false): Promise<PickResult> {
  // The system photo picker shows only what the person selects: no permission needed.
  return finish(
    await ImagePicker.launchImageLibraryAsync({
      ...options,
      allowsEditing: square,
      aspect: square ? [1, 1] : undefined,
    }),
  );
}

export async function takePhoto(square = false): Promise<PickResult> {
  const outcome = await ensurePermission(
    ImagePicker.getCameraPermissionsAsync,
    ImagePicker.requestCameraPermissionsAsync,
  );
  if (outcome !== "granted") return { kind: "permission", outcome };
  return finish(
    await ImagePicker.launchCameraAsync({
      ...options,
      allowsEditing: square,
      aspect: square ? [1, 1] : undefined,
    }),
  );
}
```

- **The result is a union, not an exception.**  `picked`, `cancelled`, `invalid` and `permission` are normal outcomes, and a screen handles each with a `switch` or a few `if`s. Cancelling is not an error.
- `quality: 0.8` makes the picker produce a smaller JPEG instead of the raw 12-megapixel original. Smaller uploads finish on a bad network, and they stay under the 10 MB limit. The picker may also convert HEIC photos (the iPhone’s default format) when it re-encodes. If it does not on your device, the next section catches it before upload.
- `allowsEditing` **with** `aspect: [1, 1]` shows a square crop screen. We use it for the avatar, which the server resizes to a square anyway (Chapter 16).

## Camera, Image Picker and Permissions › When you need your own camera screen

The system camera is the right default, but sometimes you need a custom screen: an overlay frame for a document, a different button, or a flow that stays inside your app. `expo-camera` provides `CameraView` and a hook for its permission. The permission logic is the same three states, shown as three screens:

**mobile/src/media/CameraCapture.tsx**

```
import { CameraView, useCameraPermissions } from "expo-camera";
import { useRef, useState } from "react";
import { Linking, Pressable, Text, View } from "react-native";

import { Button } from "../ui";
import type { PickedAsset } from "./mediaRules";

/** A full-screen camera. Use it when the system camera screen is not enough. */
export function CameraCapture(props: { onCapture: (asset: PickedAsset) => void; onClose: () => void }) {
  const [permission, requestPermission] = useCameraPermissions();
  const camera = useRef<CameraView>(null);
  const [taking, setTaking] = useState(false);

  if (!permission) return <View style={{ flex: 1, backgroundColor: "#000" }} />; // still checking

  if (!permission.granted) {
    return (
      <View style={{ flex: 1, justifyContent: "center", padding: 24, backgroundColor: "#fff" }}>
        <Text style={{ fontSize: 16, marginBottom: 16 }}>
          We use the camera only to photograph documents you choose to upload.
        </Text>
        {permission.canAskAgain ? (
          <Button title="Allow camera" onPress={() => void requestPermission()} />
        ) : (
          <Button title="Open Settings" onPress={() => void Linking.openSettings()} />
        )}
        <Button title="Not now" kind="plain" onPress={props.onClose} />
      </View>
    );
  }

  async function shoot() {
    if (taking) return;
    setTaking(true);
    try {
      const photo = await camera.current?.takePictureAsync({ quality: 0.7 });
      if (photo) props.onCapture({ uri: photo.uri, width: photo.width, height: photo.height, mimeType: "image/jpeg" });
    } finally {
      setTaking(false);
    }
  }

  return (
    <View style={{ flex: 1, backgroundColor: "#000" }}>
      <CameraView ref={camera} style={{ flex: 1 }} facing="back" />
      <View style={{ flexDirection: "row", justifyContent: "space-around", alignItems: "center", padding: 24 }}>
        <Pressable onPress={props.onClose} accessibilityRole="button"><Text style={{ color: "#fff", fontSize: 16 }}>Cancel</Text></Pressable>
        <Pressable onPress={shoot} accessibilityRole="button" accessibilityLabel="Take photo"
          style={{ width: 72, height: 72, borderRadius: 36, backgroundColor: "#fff", opacity: taking ? 0.5 : 1 }} />
        <View style={{ width: 48 }} />
      </View>
    </View>
  );
}
```

- `useCameraPermissions()` returns `null` while it checks, then an object with `granted` and `canAskAgain`. The component draws a black screen, then either the camera, an explanation with an “Allow camera” button, or (when `canAskAgain` is false) an “Open Settings” button.
- **The explanation says why**, in the person’s terms, before the system dialog. People who understand the reason grant far more often.
- `takePictureAsync({ quality: 0.7 })` returns a file in the app’s cache. We wrap it in the same `PickedAsset` shape as the picker, so everything after this point (validation, `toFormData`, upload) is shared.
- **Cameras use real hardware**, so the simulator and some emulators show a placeholder or a black preview. Test on a phone.
> **Photos can carry the location where they were taken**
>
> A camera photo may embed GPS coordinates in its EXIF data (Chapter 16, Section 16.5). The avatar path re-encodes the image, which removes them. Documents are stored exactly as sent, so a photo of a document taken at home and shared with another person could reveal the address. If that matters for your product, re-encode document photos on the server too: Chapter 16’s `process_avatar` is the model. This is a good example of a privacy rule that belongs on the server, because only the server can guarantee it.


## Camera, Image Picker and Permissions › Tests

The media tests check the rules the screens depend on: a normal JPEG is accepted; anything over 10 MB is refused with the actual size in the message; HEIC gets its own explanation; GIFs and empty files are refused; a missing MIME type falls back to the file extension; the form carries `{uri, name, type}`; and the three permission outcomes (including “never ask when blocked”).

**mobile/__tests__/media.test.ts (excerpt)**

```
it("refuses anything over the server limit, and says how big it was", () => {
  const verdict = validateAsset({
    uri: "file:///a.jpg",
    mimeType: "image/jpeg",
    fileSize: MAX_UPLOAD_BYTES + 1,
  });
  expect(verdict.ok).toBe(false);
  expect(!verdict.ok && verdict.message).toMatch(/10\.0 MB.*limit is 10 MB/);
});

it("describes the file as {uri, name, type}, the React Native way", () => {
  // ...with a FakeForm that records append()
  expect(appended).toEqual([
    ["file", { uri: "file:///cache/a.jpg", name: "invoice.jpg", type: "image/jpeg" }],
  ]);
});
```
