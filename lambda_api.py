from flask import Flask, request, jsonify, send_from_directory
import os
import boto3
import threading
import subprocess
import logging
import urllib.parse
import traceback
import shutil
import time
import datetime
import re
import queue
import platform
import socket

# 检测操作系统和用户
def detect_os_and_user():
    # 获取主机名
    hostname = socket.gethostname()
    
    # 检测操作系统类型
    if os.path.exists('/etc/os-release'):
        with open('/etc/os-release', 'r') as f:
            os_content = f.read().lower()
            if 'ubuntu' in os_content:
                os_type = 'ubuntu'
                default_user = 'ubuntu'
            else:
                os_type = 'amazon_linux'
                default_user = 'ec2-user'
    else:
        # 默认为 Amazon Linux
        os_type = 'amazon_linux'
        default_user = 'ec2-user'
    
    # 获取用户主目录
    user_home = f"/home/{default_user}"
    return os_type, default_user, user_home

# 获取系统信息
OS_TYPE, DEFAULT_USER, USER_HOME = detect_os_and_user()

# 创建日志目录并设置权限
log_dir = f'{USER_HOME}/logs'
os.makedirs(log_dir, exist_ok=True)
subprocess.run(['sudo', 'chown', '-R', f'{DEFAULT_USER}:{DEFAULT_USER}', log_dir], check=True)
subprocess.run(['sudo', 'chmod', '755', log_dir], check=True)

# 创建日志记录器
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 创建文件处理器
file_handler = logging.FileHandler(f'{USER_HOME}/logs/mineru_api.log')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# 添加控制台处理器
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)

# 打印启动消息
logger.info("===============================================")
logger.info("MinerU PDF处理服务启动")
logger.info(f"操作系统: {OS_TYPE}, 用户: {DEFAULT_USER}, 主目录: {USER_HOME}")
logger.info("===============================================")

app = Flask(__name__)
# 创建一个队列
request_queue = queue.Queue()

@app.errorhandler(404)
def not_found_error(error):
    """处理404错误"""
    logger.warning(f"404错误: {request.path}")
    return jsonify({
        "status": "error",
        "message": "请求的资源不存在",
        "error": str(error)
    }), 404

@app.errorhandler(400)
def bad_request_error(error):
    """处理400错误"""
    logger.warning(f"400错误: {request.path}")
    return jsonify({
        "status": "error",
        "message": "无效的请求",
        "error": str(error)
    }), 400

@app.route('/favicon.ico')
def favicon():
    """返回favicon"""
    return '', 204  # 返回无内容响应

def process_file_in_mineru_env(input_bucket, input_key, file_type):
    """处理文件并将结果上传到S3"""
    temp_dir = None
    try:
        # 创建临时目录
        temp_dir = f"/tmp/mineru_temp_{int(time.time())}"
        os.makedirs(temp_dir, exist_ok=True)

        # 创建日志目录
        logs_dir = f'{USER_HOME}/logs/mineru_pdf_logs'
        os.makedirs(logs_dir, exist_ok=True)
        log_file = os.path.join(logs_dir, f"magic_pdf_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

        # 下载文件
        decoded_key = urllib.parse.unquote_plus(input_key)
        original_filename = os.path.basename(decoded_key)
        safe_filename = original_filename.replace(' ', '_')
        local_file_path = os.path.join(temp_dir, safe_filename)

        s3_client = boto3.client('s3', region_name='cn-north-1')
        logger.info(f"下载文件: s3://{input_bucket}/{decoded_key} -> {local_file_path}")
        s3_client.download_file(input_bucket, decoded_key, local_file_path)

        # 设置输出目录
        output_dir = os.path.join(temp_dir, "output")
        os.makedirs(output_dir, exist_ok=True)

        # 查找 magic-pdf 可执行文件
        magic_pdf_path = None
        for root, dirs, files in os.walk(f"{USER_HOME}/miniconda"):
            for file in files:
                if file == "magic-pdf":
                    magic_pdf_path = os.path.join(root, file)
                    break
            if magic_pdf_path:
                break
        
        if not magic_pdf_path:
            logger.error("找不到 magic-pdf 可执行文件")
            return False
        
        logger.info(f"找到 magic-pdf 路径: {magic_pdf_path}")
        
        # 使用完整路径执行 magic-pdf 命令
        magic_pdf_cmd = [magic_pdf_path, "-p", local_file_path, "-o", output_dir, "-m", "auto"]
        
        # 执行命令
        full_cmd = ' '.join(magic_pdf_cmd)
        logger.info(f"开始执行命令: {full_cmd}")
        start_time = time.time()

        # 打开日志文件
        with open(log_file, 'w') as log_file_handle:
            # 使用Popen执行命令并捕获输出
            process = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
            logger.info(f"命令进程已启动，PID: {process.pid}")

            # 处理标准输出
            for line in process.stdout:
                line = line.strip()
                if line:  # 只处理非空行
                    logger.info(f"magic-pdf (stdout): {line}")
                    log_file_handle.write(f"{line}\n")
                    log_file_handle.flush()

            # 处理标准错误，但不标记为错误
            for line in process.stderr:
                line = line.strip()
                if line:  # 只处理非空行
                    logger.info(f"magic-pdf (stderr): {line}")  # 改为使用info级别
                    log_file_handle.write(f"{line}\n")  # 不再添加ERROR:前缀
                    log_file_handle.flush()

            # 等待进程完成
            process.wait()
            exit_code = process.returncode
            execution_time = time.time() - start_time
            logger.info(f"magic-pdf命令执行完成，返回码: {exit_code}，耗时: {execution_time:.2f}秒")

            # 如果返回码非零，才记录为错误
            if exit_code != 0:
                logger.error(f"magic-pdf命令执行失败，返回码: {exit_code}，耗时: {execution_time:.2f}秒")

        # 检查输出文件
        files = []
        has_images = False
        for root, dirs, filenames in os.walk(output_dir):
            for filename in filenames:
                local_path = os.path.join(root, filename)
                relative_path = os.path.relpath(local_path, output_dir)
                if 'images' in relative_path:
                    has_images = True
                files.append((local_path, relative_path))

        logger.info(f"共找到 {len(files)} 个输出文件")

        if not files:
            logger.warning("没有找到输出文件，处理结束")
            return False

        # 上传处理后的文件，调整S3目录结构
        name_without_suffix = os.path.splitext(original_filename)[0]
        output_prefix = f"output/{name_without_suffix}/"

        upload_count = 0
        for local_path, relative_path in files:
            # 处理图片文件：从任何子目录的images/中提取并放到根目录的images/下
            if 'images/' in relative_path:
                # 提取images/后面的部分
                image_match = re.search(r'images/(.*)', relative_path)
                if image_match:
                    image_path = image_match.group(1)
                    s3_key = f"{output_prefix}images/{image_path}"
                else:
                    # 如果无法匹配，直接使用原文件名放在images目录下
                    s3_key = f"{output_prefix}images/{os.path.basename(relative_path)}"
            else:
                # 非图片文件直接放在根目录下
                s3_key = f"{output_prefix}{os.path.basename(relative_path)}"

            try:
                s3_client.upload_file(local_path, input_bucket, s3_key)
                upload_count += 1
                logger.info(f"上传成功: s3://{input_bucket}/{s3_key}")
            except Exception as e:
                logger.error(f"上传失败: {local_path} -> {str(e)}")

        # 确保images目录存在
        if not has_images:
            s3_client.put_object(Bucket=input_bucket, Key=f"{output_prefix}images/")
            logger.info(f"创建了空的images目录: s3://{input_bucket}/{output_prefix}images/")

        # 上传日志文件到根目录
        try:
            s3_log_key = f"{output_prefix}magic_pdf_execution.log"
            s3_client.upload_file(log_file, input_bucket, s3_log_key)
            logger.info(f"上传了执行日志: s3://{input_bucket}/{s3_log_key}")
        except Exception as e:
            logger.error(f"上传日志失败: {str(e)}")

        return upload_count > 0

    except Exception as e:
        logger.error(f"处理出错: {str(e)}")
        logger.error(traceback.format_exc())
        return False
    finally:
        # 清理临时文件
        if temp_dir and os.path.exists(temp_dir):
            try:
                # 修改临时目录及其所有文件的权限
                subprocess.run(['sudo', 'chown', '-R', f'{DEFAULT_USER}:{DEFAULT_USER}', temp_dir], check=True)
                shutil.rmtree(temp_dir)
                logger.info("临时文件已清理")
            except Exception as e:
                logger.error(f"清理临时文件失败: {str(e)}")

def queue_worker():
    """队列工作线程，处理队列中的文件转换请求"""
    logger.info("队列工作线程已启动")
    while True:
        try:
            # 从队列中获取任务
            input_bucket, input_key, file_type = request_queue.get()
            logger.info(f"开始处理队列任务: {input_key}")
            start_time = time.time()
            
            # 处理文件
            result = process_file_in_mineru_env(input_bucket, input_key, file_type)
            
            execution_time = time.time() - start_time
            if result:
                logger.info(f"队列任务完成: {input_key}，总耗时: {execution_time:.2f}秒")
            else:
                logger.error(f"队列任务失败: {input_key}，总耗时: {execution_time:.2f}秒")
                
            # 标记任务完成
            request_queue.task_done()
            logger.info(f"当前队列剩余任务数: {request_queue.qsize()}")
        except Exception as e:
            logger.error(f"队列处理器出错: {str(e)}")
            logger.error(traceback.format_exc())
            # 即使出错也标记任务完成，防止队列阻塞
            try:
                request_queue.task_done()
            except:
                pass
            
            # 短暂休息后继续处理其他任务
            time.sleep(1)

@app.route('/')
def index():
    """根路径返回服务状态信息"""
    logger.info("访问根路径")
    return jsonify({
        "status": "running",
        "service": "MinerU PDF Processing Service",
        "version": "1.0",
        "endpoints": {
            "convert": "/convert (POST)",
            "health": "/health (GET)"
        },
        "queue_size": request_queue.qsize(),
        "system_info": {
            "os_type": OS_TYPE,
            "user": DEFAULT_USER,
            "home_dir": USER_HOME
        }
    })

@app.route('/convert', methods=['POST'])
def convert_file():
    """API endpoint接收转换请求"""
    try:
        data = request.json
        if not data:
            logger.warning("收到无效请求: 缺少JSON请求体")
            return jsonify({"status": "error", "message": "缺少JSON请求体"}), 400

        input_bucket = data.get('bucket')
        input_key = data.get('key')
        file_type = data.get('file_type', 'pdf')

        if not input_bucket or not input_key:
            logger.warning(f"收到无效请求: 缺少必要参数, bucket={input_bucket}, key={input_key}")
            return jsonify({"status": "error", "message": "缺少必要参数"}), 400

        logger.info(f"收到转换请求: bucket={input_bucket}, key={input_key} (类型: {file_type})")

        # 将请求放入队列
        request_queue.put((input_bucket, input_key, file_type))
        logger.info(f"请求已加入队列: {input_key}, 当前队列长度: {request_queue.qsize()}")

        return jsonify({
            "status": "queued",
            "message": f"请求 {input_key} 已加入队列等待处理",
            "queue_size": request_queue.qsize()
        })
    except Exception as e:
        logger.error(f"处理请求失败: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    logger.info("健康检查")
    return jsonify({
        "status": "healthy", 
        "message": "服务运行正常",
        "system_info": {
            "os_type": OS_TYPE,
            "user": DEFAULT_USER,
            "home_dir": USER_HOME
        },
        "queue_info": {
            "current_size": request_queue.qsize()
        }
    })

if __name__ == '__main__':
    try:
        # 启动队列工作线程
        worker_thread = threading.Thread(target=queue_worker, daemon=True)
        worker_thread.start()
        logger.info("MinerU PDF处理服务启动完成，开始监听请求")
        app.run(host='0.0.0.0', port=5000)
    except Exception as e:
        logger.critical(f"服务启动失败: {str(e)}")
        logger.critical(traceback.format_exc())