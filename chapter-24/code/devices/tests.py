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
