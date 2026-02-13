import subprocess
import json

class UsbService:
    def list_all_usb_devices(self):
        """
        Retorna dos listas de dispositivos USB:
        1. almacenamiento: discos/particiones USB con mountpoint
        2. otros: cualquier otro USB (teclados, ratones, cámaras, hubs, etc.)
        Cada dispositivo es un dict con keys: 'name', 'type', 'mount', 'dev', 'size'
        """
        storage_devices = []
        other_devices = []

        # --- Discos USB ---
        try:
            out = subprocess.check_output(
                ["lsblk", "-o", "NAME,MODEL,TRAN,MOUNTPOINT,SIZE,TYPE", "-J"], text=True
            )
            blk = json.loads(out)
            for block in blk.get("blockdevices", []):
                if block.get("tran") == "usb":
                    # Guardar disco padre
                    dev = {
                        "name": block.get("model", "USB Disk"),
                        "type": block.get("type", "disk"),
                        "mount": block.get("mountpoint"),
                        "dev": "/dev/" + block.get("name"),
                        "size": block.get("size"),
                        "children": []
                    }

                    # Guardar particiones como hijos
                    for child in block.get("children", []):
                        child_dev = {
                            "name": child.get("model") or child.get("name"),
                            "type": child.get("type"),
                            "mount": child.get("mountpoint"),
                            "dev": "/dev/" + child.get("name"),
                            "size": child.get("size")
                        }
                        dev["children"].append(child_dev)

                    storage_devices.append(dev)

        except Exception:
            pass

        # --- Otros dispositivos USB ---
        try:
            out = subprocess.check_output(["lsusb"], text=True)
            
            for line in out.strip().split("\n"):
                if line:
                    other_devices.append({"name": line, "type": "usb", "mount": None, "dev": None, "size": None})
        except Exception:
            other_devices.append({"name": "Error listando USBs", "type": "error", "mount": None, "dev": None, "size": None})

        return storage_devices, other_devices

    def parse_lsusb_line(self, line):
        """
        Convierte una línea de lsusb en algo más legible:
        'Bus 004 Device 002: ID 0b05:17eb ASUSTek Computer, Inc. USB-AC55 ...'
        → 'Bus 004 - ASUSTek Computer, Inc.: USB-AC55 ...'
        """
        parts = line.split()
        try:
            # Extraer número de bus
            bus_index = parts.index("Bus") + 1
            bus = parts[bus_index]

            # Buscar el primer elemento después del ID XXXX:YYYY
            id_index = parts.index("ID") + 2
            manufacturer = parts[id_index]
            model = " ".join(parts[id_index+1:])

            return f"Bus {bus} - {manufacturer}: {model}"
        except Exception:
            return line  # fallback si no se puede parsear
        
