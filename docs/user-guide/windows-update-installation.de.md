# Windows-Client mit Update-Inventar installieren oder aktualisieren

Diese Anleitung ergänzt [den Windows-Client](../../clients/windows/README.md)
und das [native Ubuntu-Server-Upgrade](../operations/ubuntu24.md#updates-and-recovery).
Sie führt keine Produktivaktion automatisch aus. Zuerst den Server, danach einen
Windows-Piloten aktualisieren. Vorhandene Konten, Schlüssel, Datenbanken und
DPAPI-Zustände bleiben erhalten; keine Neuinitialisierung oder erneute
Registrierung eines schon angemeldeten Clients durchführen.

## Bestehenden nativen Server aktualisieren

Als zuständiger Administrator zuerst Datenbank, `/etc/bearings` und privaten
Anwendungszustand sichern und die Wiederherstellung prüfen. Der folgende Ablauf
gilt für die bereits eingerichtete native Installation in `/opt/bearings`;
abweichende Installationen verwenden ihren bestehenden Upgrade-Prozess.

Als root ausführen. Lokale Änderungen zunächst separat prüfen; der Ablauf bricht
bei einem unsauberen Checkout ab. Den angezeigten Ziel-Commit vor dem Stoppen
gegen den veröffentlichten Merge prüfen. Der Checkout wird auf diesen festen
Commit gesetzt; kein erster Installationslauf und keine Beispiel-Daten.

```sh
set -eu
cd /opt/bearings
test -z "$(git status --porcelain)"
git fetch origin main
reviewed=$(git rev-parse FETCH_HEAD)
git show --no-patch --oneline "$reviewed"
git merge-base --is-ancestor HEAD "$reviewed"
systemctl stop bearings-web bearings-worker bearings-national
git switch --detach "$reviewed"
/opt/bearings-tools/bin/uv sync --frozen --no-dev --extra production --python /usr/bin/python3.12
./deploy/ubuntu24/manage.py migrate --noinput </dev/null
./deploy/ubuntu24/manage.py collectstatic --noinput </dev/null
./deploy/ubuntu24/manage.py check </dev/null
python3 deploy/ubuntu24/ecosystem.py prepare-clients --no-restart
systemctl start bearings-web bearings-worker bearings-national
systemctl is-active bearings-web bearings-worker bearings-national
```

Bestehende Integrationsrechte, Kunden-/Quellzuordnungen und systemd-Ausnahmen
nicht neu einrichten. Bei einem Fehler Ursache und Dienstprotokolle prüfen;
nicht trotz eines fehlgeschlagenen Schritts weiterlaufen lassen. Dieser Zusatz
benötigt keine weitere Schema-Migration nach 0074; `migrate` berücksichtigt auch
ältere noch ausstehende Migrationen. Erst nach Web-/Worker-Start die öffentlichen
HTTPS-Seiten und eine berechtigte Host-Ansicht prüfen.

## Windows herunterladen und einrichten

1. Auf dem aktualisierten Bearings-Server `/downloads/windows/` öffnen. Passendes
   ZIP für **x64**, **ARM64** oder **x86** herunterladen und den SHA-256 mit
   `SHA256SUMS` vergleichen. Die Pakete sind derzeit nicht Authenticode-signiert.
2. Unter dem späteren Meldekonto auspacken. Bei einer **Neuinstallation** die EXE
   starten und unter **Register and enable reports** den bestehenden gemeinsamen
   Linux-/Windows-Rollout-Schlüssel eingeben. Alternativ `enroll --code` verwenden.
3. Bei einem **bestehenden Client** die geplante Aufgabe pausieren, laufende
   Berichte bzw. `watch` beenden und die bisherige EXE sichern. Die EXE in
   `%LOCALAPPDATA%\Programs\Bearings\bearings-windows.exe` durch die neue Version
   ersetzen. Konto, Profil und `%LOCALAPPDATA%\Bearings\Windows` unverändert lassen.
   Bei einem abweichenden Aufgabenpfad die tatsächlich verwendete EXE ersetzen.
4. Im EXE-Verzeichnis unter demselben Konto ausführen:

```powershell
.\bearings-windows.exe --version
.\bearings-windows.exe report
.\bearings-windows.exe status
```

`Report status: applied` bestätigt den verarbeiteten Bericht. Bei `pending` später
nochmals `status` prüfen; nicht durch erneute Registrierung zusätzliche Hosts
anlegen. Danach die vorhandene Aufgabe wieder aktivieren und einmal manuell
starten. Aufgabenergebnis und Berichtsstatus getrennt kontrollieren. Die korrigierte
Task-Scheduler-Aufgabe und die neue WUA-Abfrage brauchen weiterhin einen echten
Windows-Piloten; Cross-Compilation ist keine Bestätigung der nativen Ausführung.

## Update-Ergebnisse prüfen

Im Host-Detail oder unter **Inventory clients → Linux / Windows inventory
observations** den Host öffnen. Der Abschnitt **Windows Update** zeigt:

- installierte und laut lokalem Cache ausstehende Software-Updates mit KB-Links,
  Update-ID, Revision und Kennzeichnung ausgeblendeter Updates;
- Abfragestatus, Gesamtzahl, begrenzte Liste und unvollständige Ergebnisse;
- letzte erfolgreiche automatische Windows-Update-Suche als separaten Cache-Hinweis;
- beobachteten Neustartbedarf sowie historische Ergebnisse bei Fehlern.

Der Client benötigt integriertes **Windows PowerShell 5.1** und lesbaren lokalen
Windows Update Agent. Er benötigt keine erhöhte Anmeldung und umgeht keine
Ausführungsrichtlinie. Anwendungskontrolle, deaktivierter WUA oder Zeitüberschreitung
werden als fehlende Update-Evidenz angezeigt; der Registry-Bericht bleibt möglich.
Es gibt keinen Online-Scan, Download, Patch, Neustart oder Eingriff in WSUS-/Update-
Richtlinien. Fehlende oder null ausstehende Updates beweisen keinen aktuellen
Patchstand; Treiber und die vollständige CBS/MSI-Historie sind nicht erfasst.
Die vollständigen produktbezogenen Hotpatch-/LTSC-/ESU-/CVE-Regeln bleiben offen.
