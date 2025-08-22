from . import statemapping
from datetime import datetime, timezone
import threading
from typing import Callable, Self

EventActiveState = tuple[bool, datetime] #active|inactive, begin_time

class EventQueueNode:
    __slots__ = "event", "next"
    def __init__(self, event:statemapping.Event, next:Self|None=None):
        self.event = event
        self.next = next

class EventQueue:
    __slots__ = "_head", "_tail", "_event_set"
    def __init__(self, head:EventQueueNode|None=None, tail:EventQueueNode|None=None):
        self._head = node = head
        if tail is None:
            if node is None:
                self._tail = None
            else:
                while node.next is not None:
                    node = node.next
                self._tail = node
        else:
            self._tail = tail
        self._event_set:set[str] = set()

    def __contains__(self, event:str|statemapping.Event):
        return (event.name if isinstance(event, statemapping.Event) else event) in self._event_set

    def __iter__(self):
        node = self._head
        while node is not None:
            yield node.event
            node = node.next

    def enqueue(self, event:statemapping.Event):
        self._event_set.add(event.name)
        node = EventQueueNode(event)
        if self._tail is None: #tail is None, head is None
            self._head = node
            self._tail = node
        else:
            self._tail.next = node
            self._tail = node

    def dequeue(self)->statemapping.Event|None:
        if self._head is None: #head is None, tail is None
            return None
        node = self._head
        self._head = self._head.next
        if self._head is None:
            self._tail = None
        self._event_set.remove(node.event.name)
        return node.event
    
    def skip(self, event:str|statemapping.Event, n:int=-1)->int:
        name = event.name if isinstance(event, statemapping.Event) else event
        if name not in self._event_set:
            return 0
        self._event_set.remove(name)
        count = 0
        while self._head is not None and self._head.event.name == name:
            self._head = self._head.next
            count += 1
            if count == n:
                return count
        if self._head is None or self._head.next is None:
            self._tail = self._head
            return count
        node = self._head
        lookahead = node.next.next
        while lookahead is not None:
            if node.next.event.name == name:
                node.next = lookahead
                lookahead = lookahead.next
                count += 1
                if count == n:
                    return count
                elif lookahead is None:
                    break
            node = node.next
            lookahead = lookahead.next
        self._tail = node if node.next.event.name == name else node.next
        return count

    def peek(self)->statemapping.Event|None:
        if self._head is None:
            return None
        return self._head.event

class EventNegotiator:
    def __init__(self, navstack_callback:Callable[[], statemapping.NavigatorStackFrame|None], statemap_callback:Callable[[], statemapping.StateMap], activity_update_callback:Callable[[], None]|None=None):
        self.navstack_callback = navstack_callback
        self.statemap_callback = statemap_callback
        self.activity_update_callback = activity_update_callback
        self.last_keybind_trigger = datetime.now(timezone.utc)
        self.keybind_holding = False
        self.event_activity_states:dict[str, EventActiveState] = {}
        self.active_queue = EventQueue()
        self.__activity_state_default = datetime.now(timezone.utc)
        self.wait_flag = threading.Event()
        self.background_task_wait_interval = 2.0
        self.keep_running = True
        self._update_lock = threading.Lock()

    def get_first_active(self):
        return self.active_queue.peek()

    def check_condition_state_match(self, condition:statemapping.StateMatchCondition)->bool:
        stack = self.navstack_callback()
        if stack is None or stack.state is None:
            return False
        return stack.state.name in condition.names

    def check_condition_media_match(self, condition:statemapping.MediaMatchCondition)->bool:
        stack = self.navstack_callback()
        if stack is None or stack.state is None:
            return False
        media = stack.state.media
        border = condition.location is None or condition.location == "border"
        content = condition.location is None or condition.location == "content"
        return (border and media.border_name in condition.names) or (content and media.content_name in condition.names)

    def check_condition_keybinds_idle(self, condition:statemapping.IdleCondition)->bool:
        return not self.keybind_holding and (datetime.now(timezone.utc) - self.last_keybind_trigger).total_seconds() >= condition.seconds
    
    def check_condition_active_limit(self, condition:statemapping.ActiveLimitCondition, event_name:str)->bool:
        state = self.event_activity_states.get(event_name, None)
        if state is None:
            return True
        active, started = state
        return not active or (datetime.now(timezone.utc) - started).total_seconds() < condition.seconds
    
    def check_condition_inactive(self, condition:statemapping.InactiveCondition, event_name:str)->bool:
        state = self.event_activity_states.get(event_name, None)
        if state is None:
            state = False, self.__activity_state_default
        active, started = state
        return active or (datetime.now(timezone.utc) - started).total_seconds() >= condition.seconds
    
    def check_event(self, event:statemapping.Event)->bool:
        is_active = True
        for condition in event.conditions:
            if condition.name == statemapping.CONDITION_CATEGORY_STATE_MATCH:
                is_active &= self.check_condition_state_match(statemapping.StateMatchCondition.cast(condition))
            elif condition.name == statemapping.CONDITION_CATEGORY_MEDIA_MATCH:
                is_active &= self.check_condition_media_match(statemapping.StateMatchCondition.cast(condition))
            elif condition.name == statemapping.CONDITION_CATEGORY_KEYBINDS_IDLE:
                is_active &= self.check_condition_keybinds_idle(statemapping.IdleCondition.cast(condition))
            elif condition.name == statemapping.CONDITION_CATEGORY_ACTIVE_LIMIT:
                is_active &= self.check_condition_active_limit(statemapping.ActiveLimitCondition.cast(condition), event.name)
            elif condition.name == statemapping.CONDITION_CATEGORY_INACTIVE:
                is_active &= self.check_condition_inactive(statemapping.InactiveCondition.cast(condition), event.name)
            
        if not is_active:
            return False
        return is_active
    
    def update_event_activity(self):
        with self._update_lock:
            statemap = self.statemap_callback()
            if statemap is None:
                return
            any_changes = False
            for event in statemap.events.values():
                is_active = self.check_event(event)
                state = self.event_activity_states.get(event.name, None)
                newstate = None
                if state is None:
                    if is_active:
                        newstate = self.event_activity_states[event.name] = is_active, datetime.now(timezone.utc)
                else:
                    active, _ = state
                    if is_active != active:
                        newstate = self.event_activity_states[event.name] = is_active, datetime.now(timezone.utc)
                
                if newstate is not None:
                    any_changes = True
                    if is_active:
                        if event not in self.active_queue:
                            self.active_queue.enqueue(event)
                    else:
                        self.active_queue.skip(event)
            
            if any_changes and self.activity_update_callback:
                self.activity_update_callback()

    def background_task(self):
        while self.keep_running:
            self.update_event_activity()
            if self.wait_flag.wait(self.background_task_wait_interval):
                self.wait_flag.clear()