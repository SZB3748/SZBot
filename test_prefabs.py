from prefabutil import prefabs

INSTANCE_FILE = "test_instance"
ACTION = 2

if ACTION == 0:
    p = prefabs.Prefab.from_folder("prefabs/test")
    instance = p.instantiate(dict(x="1", y="test_y_value"), INSTANCE_FILE)
elif ACTION == 1:
    prefabs.update_instance_from_file(INSTANCE_FILE, dict(y="y2"))
elif ACTION == 2:
    prefabs.delete_instance_from_file(INSTANCE_FILE)
