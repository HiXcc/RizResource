import base64
import requests
import UnityPy
import os
from zipfile import ZipFile
import json

from acbtoogg import convert_acb_to_ogg

global ssl
ssl = True
if not ssl:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class ByteReader:
    def __init__(self, data):
        self.data = data
        self.position = 0

    def readInt(self):
        self.position += 4
        return self.data[self.position - 4] ^ self.data[self.position - 3] << 8 ^ self.data[self.position - 2] << 16

def get_info(list,id) -> dict:
    for dict in list:
        if dict["id"] == id:
            return dict
    return -1

def getver():
    """返回示例:https://rizlineasset.pigeongames.net/versions/v109_2_0_9_523d8dd4e0P"""
    headers = {"game_id":"pigeongames.rizline"}
    ver = requests.get("https://rizserver.pigeongames.net/game/server_api/v1/dis",headers=headers,verify=ssl)
    """{"configs":[{"version":"2.0.9","resourceUrl":"https://rizlineasset.pigeongames.net/versions/v109_2_0_9_523d8dd4e0P","resourceBaseUrl":"https://rizlineasset.pigeongames.net/versions","resourceVersion":"v109_2_0_9_523d8dd4e0P"}],"minimalVersion":"2.0.9"}"""
    return ver.json()["configs"][0]["resourceUrl"]

def safe_string(string):
    try:
        string.encode("gbk")
        return True
    except UnicodeEncodeError:
        return False

def main():
    base_version:str = getver()
    url = f"{base_version}/Android/catalog_catalog.json"
    catalog = requests.get(f"{base_version}/Android/catalog_catalog.json",verify=ssl).json()
    base_version = base_version.split("/")[-1]
    version_list = [base_version]
    result = requests.get(f"https://rizlineasset.pigeongames.net/versions/{base_version}/patch_metadata",verify=ssl)
    last_version = base_version
    result.encoding = "utf-8"
    result = result.text
    result = result.split("\n")
    version = result[0]
    bundle_version_dict = {}
    while not version.startswith("<?xml"):
        #https://rizlineasset.pigeongames.net/versions/v101_2_0_9_fed974f1d6P/patch_metadata
        url = f"https://rizlineasset.pigeongames.net/versions/{version}/patch_metadata"
        for bundle in result[1:]:
            if bundle.startswith("Android/"):
                bundle = bundle.replace("cridata_assets_criaddressables","CriAddressables")
                bundle = bundle.replace("Android/","")
                bundle_version_dict.update({bundle:last_version})
        result = requests.get(url,verify=ssl)
        result.encoding = "utf-8"
        result = result.text
        result = result.split("\n")
        last_version = version
        version_list.insert(0,last_version)
        version = result[0]
        bundle_version_dict.update({"base_v":base_version})
    bundle_version_dict.update({"verlist":version_list})
    bundle_version_dict.update({"catalog_catalog.json":last_version})
    with open("Rizline_Resource/version_file.json","w",encoding="utf-8") as f:
        json.dump(bundle_version_dict,f,ensure_ascii=False)
    #https://rizlineasset.pigeongames.net/versions/v100_2_0_8_86e2fda4e0/Android/catalog_catalog.json
    info = info_get(bundle_version_dict.copy())
    print("info获取完毕.")
    resource_get(catalog,bundle_version_dict)
    zip_pack(info)
    print("解包完毕")

def info_get(bundle:dict):
    end = 0
    for res,ver in bundle.items():
        if isinstance(res,str):
            if not res.endswith(".bundle"):
                continue
            url = f"https://rizlineasset.pigeongames.net/versions/{ver}/Android/{res}"
            response = requests.head(url, allow_redirects=True, verify=ssl, stream=True)
            res_size = int(response.headers.get('Content-Length'))
            if 12000 < res_size < 50000000:
                continue
            if res_size < 3800:
                continue
            bundle = requests.get(url,verify=ssl,stream=True)
            env = UnityPy.load(bundle.content)  # 加载bundle文件
            for obj in env.objects:  # 遍历所有bundle的所有资源
                data = obj.read()
                if hasattr(data,"m_Name"):
                    if data.m_Name == "Default":
                        print("derf")
                        d = obj.read_typetree()
                        end += 1
                        break
                    if "zh-Hans." in data.m_Name:
                        print(data.m_Name)
                        with open(f"Rizline_Resource/{data.m_Name}.txt","wb") as tf:
                            tf.write(data.m_Script.encode())
                        end += 1
                        break
        if end >= 4:
            break
    infos = []
    for song in d["levels"]:
        id = song["id"]
        music_id:str = song["musicId"]
        ill_id = song["illustrationId"]
        chart_id = song["chartIds"]
        music_dict = get_info(d["musics"],music_id)
        ill_dict = get_info(d["illustrations"],ill_id)
        info = {"id":id,
                "chart_id":chart_id,
                "music_id":music_id,
                "illustration_id":ill_id,
                "chap":song["discName"],
                "name":music_dict["musicName"],
                "composer":music_dict["artist"],
                "pst":music_dict["previewStartTime"],
                "pet":music_dict["previewOverTime"],
                "illustrator":ill_dict["artist"],
                }
        for chart in chart_id:
            chart = get_info(d["charts"],chart)
            info.update({chart["level"]:{"diff":chart["difficulty"],
                                         "charter":chart["designer"]}})
        infos.append(info)
    with open("Rizline_Resource/info.json","w",encoding="utf-8") as default_mono:
        json.dump(infos,default_mono,ensure_ascii=False)
    with open("Rizline_Resource/default_raw.json","w",encoding="utf-8") as default_mono:
        json.dump(d,default_mono,ensure_ascii=False)

    print("info done.")
    return infos

def resource_get(data,verlist):
    dir_name = ["chart","illustration","music-acb","music-ogg","Unpack_log","zip"]
    for dir in dir_name:
        if not os.path.exists(f"Rizline_Resource/{dir}"):
            os.mkdir(f"Rizline_Resource/{dir}")
    key = base64.b64decode(data["m_KeyDataString"])
    bucket = base64.b64decode(data["m_BucketDataString"])
    entry = base64.b64decode(data["m_EntryDataString"])

    table = []
    reader = ByteReader(bucket)
    for _ in range(reader.readInt()):
        key_position = reader.readInt()
        key_type = key[key_position]
        key_position += 1
        if key_type == 0:
            length = key[key_position]
            key_position += 4
            key_value = key[key_position:key_position + length].decode()
        elif key_type == 1:
            length = key[key_position]
            key_position += 4
            key_value = key[key_position:key_position + length].decode("utf16")
        elif key_type == 4:
            key_value = key[key_position]
        else:
            raise BaseException(key_position, key_type)
        for i in range(reader.readInt()):
            entry_position = reader.readInt()
            entry_value = entry[4 + 28 * entry_position:4 + 28 * entry_position + 28]
            entry_value = entry_value[8] ^ entry_value[9] << 8
        table.append([key_value, entry_value])
        
    for i in range(len(table)):
        if table[i][1] != 65535:
            table[i][1] = table[table[i][1]][0]

    Resource = []
    extra = []

    for i in range(len(table) - 1, -1, -1):
        if type(table[i][0]) != str or type(table[i][1]) != str:
            del table[i]
            continue
        if table[i][0][:5] == "chart":
            Resource.append(table[i])
        elif table[i][0][:12] == "illustration" and table[i][0][-5:] != "HiRes":
            Resource.append(table[i])
        elif table[i][0][:16] == "CriAddressables/":
            Resource.append(table[i])
        else:
            extra.append(table[i])
    
    with open("Rizline_Resource/Unpack_log/all_resource","w",encoding="utf-8") as f:
        for i in range(len(Resource)):
            f.write(str(Resource[i])+"\n")  # 记录所有符合的资源
        for i in range(len(extra)):
            f.write(str(extra[i])+"\n")

    with open("Rizline_Resource/Unpack_log/chart_log","w",encoding="utf-8") as f:
        for i in range(len(Resource)):
            if Resource[i][0][:5] == "chart":
                f.write(str(Resource[i])+"\n")  # 记录所有符合的谱面资源
    
    with open("Rizline_Resource/Unpack_log/illustration_log","w",encoding="utf-8") as f:
        for i in range(len(Resource)):
            if Resource[i][0][:12] == "illustration":
                f.write(str(Resource[i])+"\n")  # 记录所有符合的曲绘资源
    
    with open("Rizline_Resource/Unpack_log/music_log","w",encoding="utf-8") as f:
        for i in range(len(Resource)):
            if Resource[i][0][:16] == "CriAddressables/":
                f.write(str(Resource[i])+"\n")  # 记录所有符合的音乐资源

    # 谱面示例:['chart.CrazyAudiophile.Supa7onyz.0.IN', '12523ede2bc20dcc4a7822bdd566d2ee.bundle']
    # 音频示例:['CriAddressables/onandon.etia.0.acb=367a00', 'cridata_assets_criaddressables/onandon.etia.0.acb=367a00_7befa38d3fd5cd186b258db5e6641db1.bundle']
    # 曲绘示例:['illustration.SwingSweetTweeDance.Uske.0.HiRes', '403502c402c4be614dd148d6c1738d31.bundle']
    # bundle文件内含有该谱面

    for key, entry in Resource:
        key:str;entry:str
        if key in verlist:
            ver = verlist[key]
        elif entry in verlist:
            ver = verlist[entry]
        else:
            ver = verlist["catalog_catalog.json"]
        if os.path.exists("Rizline_Resource/chart/%s.json"%key):
            continue
        if os.path.exists("Rizline_Resource/illustration/%s.png"%key):
            continue
        if key.startswith(("chart","illustration")):
            url = f"https://rizlineasset.pigeongames.net/versions/{ver}/Android/{entry}"
        elif key.startswith("CriAddressables/") and not entry.startswith("crilocaldata_assets_all"):
            path = key[16:]
            file_name = path[:-7]
            if not safe_string(file_name):
                file_name = file_name.encode("gbk",errors="ignore").decode("utf-8")
            if os.path.exists(f"Rizline_Resource/music-ogg/{file_name[:-4]}.ogg"):
                continue
            url = f"https://rizlineasset.pigeongames.net/versions/{ver}/Android/cridata_assets_criaddressables/{path}"
            music_data = requests.get(url,verify=ssl)
            if music_data.status_code == 404:
                for ver in verlist["verlist"]:
                    music_data = requests.get(url,verify=ssl)
                    if music_data.status_code != 404:
                        break
            with open(f"Rizline_Resource/music-acb/{file_name}","wb") as m:
                m.write(music_data.content)
            continue
        else:
            continue
        bundle = requests.get(url,verify=ssl)
        env = UnityPy.load(bundle.content)  # 加载bundle文件
        for obj in env.objects:  # 遍历所有bundle的所有资源
            data = obj.read()
            if obj.type.name == "TextAsset":  # 若为文字资源
                content = data.m_Script.encode()
                with open("Rizline_Resource/chart/%s.json"%key, "wb") as f:
                    f.write(content)
            if obj.type.name == "Texture2D":
                data.image.save("Rizline_Resource/illustration/%s.png"%key)
    
    for music_acb in os.listdir("Rizline_Resource/music-acb/"):
        if not safe_string(music_acb):
            music_acb = music_acb.encode("gbk",errors="ignore").decode("utf-8")
        if not convert_acb_to_ogg(f"Rizline_Resource/music-acb/{music_acb}", "Rizline_Resource/music-ogg"):
            print(f"error:{music_acb}")
        else:
            os.remove(f"Rizline_Resource/music-acb/{music_acb}")

    print("resource done.")

def zip_pack(infos):
    #打包
    diffs = ["","EZ","HD","IN","AT"]
    for diff in diffs[1:]:
        if not os.path.isdir(f"Rizline_Resource/zip/{diff}/"):
            os.mkdir(f"Rizline_Resource/zip/{diff}")
    for song_info in infos:
        for temp_diff in diffs[::-1]:
            if temp_diff in song_info:
                real_song_info = {"name":song_info["name"],
                                "composer":song_info["composer"],
                                "illustrator":song_info["illustrator"],
                                "diff":song_info[temp_diff]["diff"],
                                "charter":song_info[temp_diff]["charter"]}
                music_id = song_info["music_id"].lower()
                if not safe_string(music_id):
                    music_id = music_id.encode("gbk",errors="ignore").decode("utf-8")
                with ZipFile(f"Rizline_Resource/zip/{temp_diff}/{song_info["id"]}.zip","w") as chart_zip:
                    chart_zip.write(f"Rizline_Resource/chart/{song_info["chart_id"][-1]}.json",arcname="chart.json")
                    chart_zip.write(f"Rizline_Resource/music-ogg/{music_id}.wav",arcname="music.ogg")
                    chart_zip.write(f"Rizline_Resource/illustration/{song_info["illustration_id"]}.png",arcname="illustration.png")
                    chart_zip.writestr("info",json.dumps(real_song_info))
    
    print("pack done.")

if __name__ == "__main__":
    main()
