import os
import subprocess
import sys
import glob

def convert_acb_to_ogg(acb_path, output_dir, vgmstream_path="vgmstream-cli.exe"):
    if not os.path.isfile(acb_path):
        print(f"错误: ACB文件不存在 - {acb_path}")
        return False
    
    if not os.path.isfile(vgmstream_path):
        print(f"错误: vgmstream-cli.exe未找到 - {vgmstream_path}")
        return False
    
    os.makedirs(output_dir, exist_ok=True)
    
    base_name = os.path.basename(acb_path)
    file_name_without_ext = os.path.splitext(base_name)[0]
    output_file = f"{file_name_without_ext}.ogg"
    output_path = os.path.join(output_dir, output_file)
    
    command = [
        vgmstream_path,
        "-o", output_path,
        acb_path
    ]
    
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        
        if os.path.isfile(output_path):
            print(f"{output_path}")
            return True
        else:
            print("错误: 转换失败，未生成输出文件")
            print("vgmstream输出信息:")
            print(result.stdout)
            print(result.stderr)
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"转换失败，错误代码: {e.returncode}")
        print("错误信息:")
        print(e.stderr)
        return False
    except Exception as e:
        print(f"发生未知错误: {str(e)}")
        return False

if __name__ == "__main__":
    music_dir = "music"
    output_dir = "output"
    vgmstream_path = "vgmstream-cli.exe"
    acb_files = glob.glob(os.path.join(music_dir, "*.acb"))
    
    convert_acb_to_ogg("夢厭coneleganza.大前司.0.acb", output_dir, vgmstream_path)