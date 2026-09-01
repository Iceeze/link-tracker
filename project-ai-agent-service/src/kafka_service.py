from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer, AvroDeserializer
from confluent_kafka.serialization import SerializationContext, MessageField

RAW_UPDATE_SCHEMA = """
{
  "type": "record",
  "name": "RawUpdateMessage",
  "fields": [
    {"name": "id", "type": "long"},
    {"name": "url", "type": "string"},
    {"name": "author", "type": "string"},
    {"name": "description", "type": "string"},
    {"name": "tgChatIds", "type": {"type": "array", "items": "long"}}
  ]
}
"""

PROCESSED_UPDATE_SCHEMA = """
{
  "type": "record",
  "name": "ProcessedUpdateMessage",
  "fields": [
    {"name": "id", "type": "long"},
    {"name": "url", "type": "string"},
    {"name": "description", "type": "string"},
    {"name": "tgChatIds", "type": {"type": "array", "items": "long"}},
    {"name": "priority", "type": "string"}
  ]
}
"""


class KafkaService:
    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        input_topic: str,
        output_topic: str,
        schema_registry_url: str,
    ):
        self.consumer = AIOKafkaConsumer(
            input_topic,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            auto_offset_reset="earliest",
        )
        self.producer = AIOKafkaProducer(bootstrap_servers=bootstrap_servers)

        self.schema_registry_client = SchemaRegistryClient({"url": schema_registry_url})
        self.avro_deserializer = AvroDeserializer(
            self.schema_registry_client,
            schema_str=RAW_UPDATE_SCHEMA,
        )
        self.avro_serializer = AvroSerializer(
            self.schema_registry_client,
            schema_str=PROCESSED_UPDATE_SCHEMA,
        )

        self.input_topic = input_topic
        self.output_topic = output_topic

    async def start(self):
        await self.consumer.start()
        await self.producer.start()

    async def stop(self):
        await self.consumer.stop()
        await self.producer.stop()

    async def send_message(self, topic: str, value: bytes):
        await self.producer.send_and_wait(topic, value=value)

    async def consume(self):
        async for msg in self.consumer:
            yield msg

    async def deserialize(self, data):
        ctx = SerializationContext(self.input_topic, MessageField.VALUE)
        return self.avro_deserializer(data, ctx)

    async def serialize(self, data):
        ctx = SerializationContext(self.output_topic, MessageField.VALUE)
        return self.avro_serializer(data, ctx)
