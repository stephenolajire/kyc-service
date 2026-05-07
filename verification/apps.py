from django.apps import AppConfig


class VerificationConfig(AppConfig):
    name = 'verification'

    def ready(self):
        from deepface import DeepFace
        DeepFace.build_model("Facenet")