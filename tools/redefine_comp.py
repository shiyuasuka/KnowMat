try:
    from pymatgen.core import Composition
except ImportError:
    print("pymatgen is not installed. Please install it to use this tool.")
    exit(1)


from pymatgen.core import Composition
import json

def redefine_comp(json_pth, isPercent=True):
    """读取标注 JSON 中的标准化化学式，并返回元素配比字典。"""
    with open(json_pth, 'r') as f:
        data = json.load(f)
        # 从数据中读取标准化化学式
        Formula_Normalized = data['Materials'][0]['Formula_Normalized']
        # 使用 pymatgen 将化学式转换为元素摩尔分数
        compsition_dict = Composition(Formula_Normalized).fractional_composition.as_dict()
        if isPercent:
            # 可选：将分数转换为百分比并保留两位小数
            for key in compsition_dict:
                compsition_dict[key] = round(compsition_dict[key] * 100, 2)
    return compsition_dict

if __name__ == "__main__":
    # 示例：读取手工标注结果并打印元素组成
    json_pth = "手工标注结果/1-data.json"
    print(redefine_comp(json_pth))
