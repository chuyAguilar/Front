import paho.mqtt.client as mqtt
import json 

def al_conectar(client, userdata, flags, reason_code, properties):
    print("conectado al broker")
    client.subscribe("monitoreo/#")  
def al_mensaje(client, userdata, msg):
    datos=json.loads(msg.payload.decode())
    if "signos" in datos:
        print("cama: ",datos["cama_id"],"fc= ",datos["signos"]["fc"]["valor"])
    else:
        print("no hay datos")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = al_conectar
client.on_message = al_mensaje
client.connect("100.110.157.112", 1883)
client.loop_forever()