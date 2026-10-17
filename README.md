# hds-mirror

Miroir plein écran de l'écran d'un OWON HDS2202S sur Linux (Debian 13). Affichage seul, tout le paramétrage se fait sur le HDS.

Le firmware V1.2.0 n'expose pas le mode courant en SCPI : quand tu appuies sur **Mode** sur le HDS,
appuie aussi sur **M** sur le PC (OSC → DMM → GEN).

```bash
sudo apt install -y python3-venv libusb-1.0-0 just
sudo usermod -aG dialout $USER      # puis se reconnecter
just setup
just check                           # le scope doit apparaître en /dev/ttyUSB0
just run                             # M mode suivant, F11 plein écran, Esc fenêtré, Q quitter
```

Un seul fichier : `hds_mirror.py`. Protocole : SCPI sur USB-série, une commande = une écriture,
réponses binaires précédées d'un en-tête de 4 octets (longueur, little-endian).
