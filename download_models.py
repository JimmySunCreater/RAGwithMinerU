import json
import os

import requests
from modelscope import snapshot_download


def download_json(url):
    # 下载JSON文件
    response = requests.get(url)
    response.raise_for_status()  # 检查请求是否成功
    return response.json()


def download_and_modify_json(url, local_filename, modifications):
    if os.path.exists(local_filename):
        data = json.load(open(local_filename))
        config_version = data.get('config_version', '0.0.0')
        if config_version < '1.1.1':
            data = download_json(url)
    else:
        data = download_json(url)

    # 修改内容
    for key, value in modifications.items():
        data[key] = value

    # 保存修改后的内容
    with open(local_filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def download_models():
    # 强制指定配置文件位置为 ec2-user 的主目录
    config_file = '/home/ec2-user/magic-pdf.json'
    
    # 下载模型
    model_dir = snapshot_download('damo/nlp_structbert_backbone_base_std', cache_dir='/home/ec2-user/.cache/modelscope')
    print(f"模型下载完成: {model_dir}")
    
    # 修改配置文件
    config = {
        "model_path": model_dir,
        "device": "cuda" if os.system("nvidia-smi") == 0 else "cpu"
    }
    
    # 确保目录存在
    os.makedirs(os.path.dirname(config_file), exist_ok=True)
    
    # 写入配置文件
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=4)
    print(f"配置文件已更新: {config_file}")
    
    # 如果是 root 用户运行，修改文件所有权
    if os.geteuid() == 0:
        os.system(f"chown ec2-user:ec2-user {config_file}")
        os.system(f"chown -R ec2-user:ec2-user /home/ec2-user/.cache/modelscope")


if __name__ == '__main__':
    mineru_patterns = [
        "models/Layout/LayoutLMv3/*",
        "models/Layout/YOLO/*",
        "models/MFD/YOLO/*",
        "models/MFR/unimernet_small_2501/*",
        "models/TabRec/TableMaster/*",
        "models/TabRec/StructEqTable/*",
    ]
    model_dir = snapshot_download('opendatalab/PDF-Extract-Kit-1.0', allow_patterns=mineru_patterns)
    layoutreader_model_dir = snapshot_download('ppaanngggg/layoutreader')
    model_dir = model_dir + '/models'
    print(f'model_dir is: {model_dir}')
    print(f'layoutreader_model_dir is: {layoutreader_model_dir}')

    json_url = 'https://gcore.jsdelivr.net/gh/opendatalab/MinerU@master/magic-pdf.template.json'
    config_file_name = 'magic-pdf.json'
    # 总是使用 ec2-user 的主目录
    config_file = '/home/ec2-user/magic-pdf.json'

    json_mods = {
        'models-dir': model_dir,
        'layoutreader-model-dir': layoutreader_model_dir,
    }

    download_and_modify_json(json_url, config_file, json_mods)
    print(f'The configuration file has been configured successfully, the path is: {config_file}')
    
    # 确保文件权限正确
    os.chmod(config_file, 0o644)
    if os.geteuid() == 0:  # 如果是 root 用户运行
        import pwd
        ec2_user_uid = pwd.getpwnam('ec2-user').pw_uid
        ec2_user_gid = pwd.getpwnam('ec2-user').pw_gid
        os.chown(config_file, ec2_user_uid, ec2_user_gid)

    download_models() 