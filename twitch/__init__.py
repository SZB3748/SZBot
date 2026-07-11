from . import analytics, bits_triggers, command_triggers, event_triggers, follow_triggers, \
    hypetrain_triggers, message_triggers, raid_triggers, redeem_triggers, sub_triggers, tronix_integrations


def enable_event_triggers(value:bool):
    bits_triggers.ActionBitsUseTrigger.enabled(value)
    bits_triggers.ActionCheerTrigger.enabled(value)
    command_triggers.ActionCommandTrigger.enabled(value)
    follow_triggers.ActionFollowTrigger.enabled(value)
    hypetrain_triggers.ActionHypeTrainBeginTrigger.enabled(value)
    hypetrain_triggers.ActionHypeTrainProgressTrigger.enabled(value)
    hypetrain_triggers.ActionHypeTrainEndTrigger.enabled(value)
    message_triggers.ActionMessageTrigger.enabled(value)
    raid_triggers.ActionRaidTrigger.enabled(value)
    redeem_triggers.ActionRedeemTrigger.enabled(value)
    sub_triggers.ActionSubTrigger.enabled(value)
    sub_triggers.ActionSubMessageTrigger.enabled(value)
    sub_triggers.ActionGiftSubTrigger.enabled(value)