"""python3 -m pod_locuri capacitate [--config F]   -> câte apeluri simultane duce serverul acum (doar citire)
   python3 -m pod_locuri plan N                     -> ce sunet/Chrome ar folosi locul N (doar afișare)
   python3 -m pod_locuri ruleaza [--config F]       -> managerul de locuri pe server (ciclul la 60 s)"""
import argparse
import json
import time

from .locuri import Manager, descrie_loc, comenzi_sunet, comanda_chrome
from .resurse import Config, calculeaza


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("comanda", choices=["capacitate", "plan", "ruleaza"])
    p.add_argument("numar", nargs="?", type=int, default=2)
    p.add_argument("--config", default="/etc/kelion-pod/locuri.json")
    a = p.parse_args()
    if a.comanda == "capacitate":
        cfg = Config(a.config)
        cfg.actualizeaza()
        print(json.dumps(calculeaza(cfg.valori).ca_dict(), ensure_ascii=False, indent=1))
    elif a.comanda == "plan":
        loc = descrie_loc(a.numar)
        env, args = comanda_chrome(loc)
        print(json.dumps({"loc": loc.ca_dict(), "sunet": comenzi_sunet(loc), "chrome_env": env, "chrome": args},
                         ensure_ascii=False, indent=1))
    else:
        from .executor_server import ExecutorServer
        m = Manager(ExecutorServer(), a.config)
        while True:
            m.sincronizeaza()
            time.sleep(60)


if __name__ == "__main__":
    main()
