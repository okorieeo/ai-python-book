python manage.py shell
>>> from django.contrib.auth import get_user_model
>>> from chat import services
>>> ada = get_user_model().objects.first()
>>> conv = services.create_conversation(user=ada, title="My first service call")
>>> services.add_user_message(conversation=conv, content="Hello!")
>>> services.save_assistant_reply(conversation=conv, text="Hi there", input_tokens=12, output_tokens=8, model_name="demo")
>>> services.tokens_used_this_month(user=ada)
20
