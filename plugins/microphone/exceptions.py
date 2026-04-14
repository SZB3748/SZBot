class MicrophoneException(Exception):
    "Base class for microphone plugin exceptions."

class MicDisabledException(MicrophoneException):
    "Tried to use a disabled microphone."

class BadMicSettingsException(MicrophoneException):
    "Microphone is configured with bad settings."