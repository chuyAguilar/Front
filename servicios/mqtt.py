import paho.mqtt.client as mqtt
import json


class ClienteMQTT:
    def __init__(self, al_vitales, al_estado, al_estado_cama):
        super().__init__()
        self.al_vitales = al_vitales
        self.al_estado = al_estado
        self.al_estado_cama = al_estado_cama

    def iniciar(self):

        def al_conectar(client, userdata, flags, reason_code, properties):
            try:
                client.subscribe("monitoreo/#")
                self.al_estado(True)
                print("conectado al broker")
            except:
                print("error al conectar al broker")

        def al_desconectar(client, userdata, flags, reason_code, properties):
            self.al_estado(False)
            print("broker no conectado")

            

        def al_mensaje(client, userdata, msg):
            datos = json.loads(msg.payload.decode())
            if "signos" in datos:
                self.al_vitales(datos["cama_id"], datos["signos"])
            elif "estado" in datos:
                self.al_estado_cama(datos["cama_id"], datos["estado"])
            else:
                print("no hay datos")
                
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.on_connect = al_conectar
        client.on_message = al_mensaje
        client.on_disconnect = al_desconectar
        #ruta real
        client.connect_async("100.110.157.112", 1883,keepalive=15)
        client.loop_start()
