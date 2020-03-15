from mqtt.mqtt_packet_types import WillQoS
from mqtt.topic_matcher import TopicMatcher

class TopicSubscription:
    def __init__(self, order, topic, qos=0):
        super().__init__()
        self.order = order
        self.topic = topic
        self.qos   = qos

    def __str__(self):
        return "'{0}' ({1})".format(self.topic, self.qos)

    __repr__ = __str__

    def __lt__(self, other):
        return self.order < other.order

    def __le__(self, other):
        return self.order <= other.order

    def __eq__(self, other):
        return self.order == other.order

    def __gt__(self, other):
        return self.order > other.order

    def __ge__(self, other):
        return self.order >= other.order

    def matches(self, topic):
        print("Subscribed topic: " + self.topic)
        print("Check topic: " + self.topic)

        # check for complete match
        if    TopicMatcher.WILDCARD_ANY not in a_filter \
          and TopicMatcher.WILDCARD_SIG not in a_filter:
            return self.topic == topic
        
        
        return self.topic == topic

    def update_qos(self, qos):
        self.qos = qos if qos in WillQoS.CHECK_VALID else 0

    @staticmethod
    def filter_wildcards(topic_name):
        # TODO
        return topic_name
