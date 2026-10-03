# spawn boAt Crest with the unpinning bundle loaded
import frida, sys, time, pathlib
dev = frida.get_device_manager().add_remote_device("127.0.0.1:27042")
pid = dev.spawn(["com.coveiot.android.boat"])
s = dev.attach(pid)
sc = s.create_script(pathlib.Path(__file__).with_name("bundle.js").read_text())
sc.on("message", lambda m, d: print(m.get("payload", m), flush=True))
sc.load(); dev.resume(pid); print("running pid", pid, flush=True)
while True: time.sleep(5)
