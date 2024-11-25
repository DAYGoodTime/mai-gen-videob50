import json
import os
import random
import time
import yaml
from update_music_data import fetch_music_data
from gene_images import generate_b50_images
from utils.Utils import get_b50_data_from_fish
from utils.video_crawler import PurePytubefixDownloader, download_video

def update_b50_data(b50_raw_file, b50_data_file, username):
    try:
        fish_data = get_b50_data_from_fish(username)
    except json.JSONDecodeError:
        print("Error: 读取 JSON 文件时发生错误，请检查数据格式。")
        return None 
    if 'error' in fish_data:
        print(f"Error: 从水鱼获得B50数据失败。错误信息：{fish_data['error']}")
        return None
    
    charts_data = fish_data['charts']
    # user_rating = fish_data['rating']
    # user_dan = fish_data['additional_rating']
    b35_data = charts_data['sd']
    b15_data = charts_data['dx']

    # 缓存，写入b50_raw_file
    with open(b50_raw_file, "w", encoding="utf-8") as f:
        json.dump(fish_data, f, ensure_ascii=False, indent=4)

    for i in range(len(b35_data)):
        song = b35_data[i]
        song['clip_id'] = f"PastBest_{i + 1}"

    for i in range(len(b15_data)):
        song = b15_data[i]
        song['clip_id'] = f"NewBest_{i + 1}"
    
    # 合并b35_data和b15_data到同一列表
    b50_data = b35_data + b15_data
    new_local_b50_data = []
    # 检查是否已有b50_data_file
    if os.path.exists(b50_data_file):
        with open(b50_data_file, "r", encoding="utf-8") as f:
            local_b50_data = json.load(f)
            assert len(b50_data) == len(local_b50_data), f"本地b50_data与从水鱼获取的数据长度不一致，请考虑删除本地{b50_data_file}缓存文件后重新运行。"
            
            # 创建本地数据的复合键映射表
            local_song_map = {
                (song['song_id'], song['level_index'], song['type']): song 
                for song in local_b50_data
            }
            
            # 按新的b50_data顺序重组local_b50_data
            for new_song in b50_data:
                song_key = (new_song['song_id'], new_song['level_index'], new_song['type'])
                if song_key in local_song_map:
                    # 如果记录已存在，保留原有数据（包括已抓取的视频信息）
                    cached_song = local_song_map[song_key]
                    cached_song['clip_id'] = new_song['clip_id']
                    new_local_b50_data.append(cached_song)
                else:
                    # 如果是新记录，使用新数据
                    new_local_b50_data.append(new_song)  
    else:
        new_local_b50_data = b50_data

    # 写入b50_data_file
    with open(b50_data_file, "w", encoding="utf-8") as f:
        json.dump(new_local_b50_data, f, ensure_ascii=False, indent=4)
    return new_local_b50_data


def search_b50_videos(b50_data, b50_data_file, search_max_results, proxy=None):
    if proxy:
        downloader = PurePytubefixDownloader(proxy)
    else:
        downloader = PurePytubefixDownloader()

    i = 0
    for song in b50_data:
        i += 1
        # Skip if video info already exists and is not empty
        if 'video_info_match' in song and song['video_info_match']:
            print(f"跳过({i}/50): {song['title']} ，已储存有相关视频信息")
            continue
        title_name = song['title']
        difficulty_name = song['level_label']
        type = song['type']
        if type == "SD":
            keyword = f"{title_name} {difficulty_name} AP【maimaiでらっくす外部出力】"
        else:
            keyword = f"{title_name} DX譜面 {difficulty_name} AP【maimaiでらっくす外部出力】"

        print(f"正在搜索视频({i}/50): {keyword}")
        videos = downloader.search_video(keyword, max_results=search_max_results)

        if len(videos) == 0:
            print(f"Error: 没有找到{title_name}-{difficulty_name}-{type}的视频")
            song['video_info_list'] = []
            song['video_info_match'] = {}
            continue

        match_index = 0
        print(f"首个搜索结果({i}/50): {videos[match_index]['title']}, {videos[match_index]['url']}")

        song['video_info_list'] = videos
        song['video_info_match'] = videos[match_index]

        # 每次搜索后都写入b50_data_file
        with open(b50_data_file, "w", encoding="utf-8") as f:
            json.dump(b50_data, f, ensure_ascii=False, indent=4)
        
        # 等待10-15秒，以减少被检测为bot的风险
        time.sleep(random.randint(10, 15))
    
    return b50_data


def download_b50_videos(b50_data, video_download_path):
    i = 0
    for song in b50_data:
        i += 1
        # 视频命名为song['song_id']-song['level_index']-song['type']，以便查找复用
        clip_name = f"{song['song_id']}-{song['level_index']}-{song['type']}"
        
        # Check if video already exists
        video_path = os.path.join(video_download_path, f"{clip_name}.mp4")
        if os.path.exists(video_path):
            print(f"已找到谱面视频的缓存({i}/50): {clip_name}")
            continue
            
        print(f"正在下载视频({i}/50): {clip_name}……")
        if 'video_info_match' not in song or not song['video_info_match']:
            print(f"Error: 没有{song['title']}-{song['level_label']}-{song['type']}的视频信息，Skipping………")
            continue
        video_info = song['video_info_match']
        download_video(video_info['url'], 
                        output_name=clip_name, 
                        output_path=video_download_path, 
                        high_res=False)
        print("\n")


def gene_resource_config(b50_data, images_path, videoes_path, ouput_file, random_length=False):
    data = []
    for song in b50_data:
        if not song['clip_id']:
            print(f"Error: 没有找到 {song['title']}-{song['level_label']}-{song['type']} 的clip_id，请检查数据格式，跳过该片段。")
            continue
        id = song['clip_id']
        video_name = f"{song['song_id']}-{song['level_index']}-{song['type']}"
        __image_path = os.path.join(images_path, id + ".png")
        __image_path = os.path.normpath(__image_path)
        if not os.path.exists(__image_path):
            print(f"Error: 没有找到 {id}.png 图片，请检查本地缓存数据。")
            __image_path = ""

        __video_path = os.path.join(videoes_path, video_name + ".mp4")
        __video_path = os.path.normpath(__video_path)
        if not os.path.exists(__video_path):
            print(f"Error: 没有找到 {video_name}.mp4 视频，请检查本地缓存数据。")
            __video_path = ""
        
        if random_length:
            duration = random.randint(10, 12)
            start = random.randint(15, 85)
            end = start + duration
        else:
            # TODO:可配置
            duration = 15
            start = 10
            end = 25

        sub_data = {
            "id": id,
            "achievement_title": f"{song['title']}-{song['level_label']}-{song['type']}",
            "background": __image_path,
            "video": __video_path,
            "duration": duration,
            "start": start,
            "end": end,
            "text": "这个人很懒，没有写b50评价。"
        }
        data.append(sub_data)

    with open(ouput_file, 'w', encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

    return data


def pre_gen():
    print("#####【mai-genb50视频生成器 - Step1 信息预处理和素材获取】#####")

    print("#####【尝试从水鱼获取乐曲更新数据】 #####")
    try:
        fetch_music_data()
    except Exception as e:
        print(f"Error: 获取乐曲更新数据时发生异常: {e}")

    # read global_config.yaml file 
    with open("./global_config.yaml", "r", encoding="utf-8") as f:
        global_config = yaml.load(f, Loader=yaml.FullLoader)

    username = global_config["USER_ID"]
    use_proxy = global_config["USE_PROXY"]
    proxy = global_config["HTTP_PROXY"]
    search_max_results = global_config["SEARCH_MAX_RESULTS"]
    use_all_cache = global_config["USE_ALL_CACHE"]

    print(f"当前查询的水鱼用户名: {username}")

    # 创建缓存文件夹
    cache_pathes = [
        f"./b50_datas",
        f"./b50_images",
        f"./videos",
        f"./videos/downloads",
    ]
    for path in cache_pathes:
        if not os.path.exists(path):
            os.makedirs(path)

    b50_raw_file = f"./b50_datas/b50_raw_{username}.json"
    b50_data_file = f"./b50_datas/b50_config_{username}.json"

    print("#####【1/4】获取用户的b50数据 #####")
    b50_data = update_b50_data(b50_raw_file, b50_data_file, username)

    print("#####【2/4】搜索b50视频信息 #####")
    try:
        if use_proxy:
            b50_data = search_b50_videos(b50_data, b50_data_file, search_max_results, proxy)
        else:
            b50_data = search_b50_videos(b50_data, b50_data_file, search_max_results)
    except Exception as e:
        print(f"Error: 搜索视频信息时发生异常: {e}")
        return -1
    
    # 下载谱面确认视频
    print("#####【3/4】下载谱面确认视频 #####")
    video_download_path = f"./videos/downloads"  # 不同用户的视频缓存均存放在downloads文件夹下
    try:
        download_b50_videos(b50_data, video_download_path)
    except Exception as e:
        print(f"Error: 下载视频时发生异常: {e}")
        return -1
    

    # 生成b50图片
    print("#####【4/4】生成b50背景图片 #####")
    image_output_path = f"./b50_images/{username}"
    if not os.path.exists(image_output_path):
        os.makedirs(image_output_path)

    # # check if image_output_path has png files
    # if len(os.listdir(image_output_path)) != 0:
    #     # delete all files in image_output_path
    #     for file in os.listdir(image_output_path):
    #         os.remove(os.path.join(image_output_path, file))

    b35_data = b50_data[:35]
    b15_data = b50_data[35:]
    try:
        generate_b50_images(username, b35_data, b15_data, image_output_path)
    except Exception as e:
        print(f"Error: 生成图片时发生异常: {e}")
        return 1
    
    # 配置视频生成的配置文件
    config_output_file = f"./b50_datas/video_configs_{username}.json"
    try:
        configs = gene_resource_config(b50_data, image_output_path, video_download_path, 
                                   config_output_file, random_length=True)
    except Exception as e:
        print(f"Error: 生成视频配置时发生异常: {e}")
        return 1
    # TODO：一个web前端可以改变配置和选择视频片段的长度

    print(f"#####【预处理完成, 请在{config_output_file}中检查生成的配置数据并填写评论】 #####")
    return 0


if __name__ == "__main__":
    pre_gen()
    
