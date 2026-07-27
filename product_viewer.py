# -*- coding: utf-8 -*-
"""
看货表桌面软件
功能：商品价目表浏览、输入数量、自动计算总价、搜索筛选、
      导出CSV、打印清单、复制摘要、新增/删除商品
运行：python product_viewer.py
数据：同目录下 products.json
"""

import json
import os
import csv
import tempfile
import webbrowser
import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# ============================================================
# 数据加载 & 保存
# ============================================================

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "products.json")


def load_data():
    """读取商品数据 JSON"""
    if not os.path.exists(DATA_FILE):
        return {"shop_name": "我的店铺", "categories": []}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    """保存商品数据到 JSON"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================
# 主窗口
# ============================================================

class ProductViewerApp:
    def __init__(self, root):
        self.root = root
        self.data = load_data()
        self.shop_name = self.data.get("shop_name", "我的店铺")
        self.categories = self.data.get("categories", [])

        # 所有商品扁平化列表：每项 = {cat, name, spec, unit, price, qty, checked}
        self.all_items = []
        for cat in self.categories:
            for p in cat.get("products", []):
                self.all_items.append({
                    "cat": cat["name"],
                    "name": p["name"],
                    "spec": p.get("spec", ""),
                    "unit": p.get("unit", ""),
                    "price": float(p.get("price", 0)),
                    "qty": 0,
                    "checked": False,
                })

        # 当前筛选状态
        self.current_cat = "全部商品"
        self.search_kw = ""

        self._build_ui()
        self._refresh_table()

    # --------------------------------------------------------
    # UI 构建
    # --------------------------------------------------------
    def _build_ui(self):
        self.root.title(f"{self.shop_name} - 看货表")
        self.root.geometry("960x620")
        self.root.minsize(800, 500)

        # 顶部栏：店铺名 + 搜索
        top = ttk.Frame(self.root, padding=(10, 8))
        top.pack(fill="x")

        ttk.Label(top, text=self.shop_name, font=("Microsoft YaHei", 16, "bold")).pack(side="left")

        right = ttk.Frame(top)
        right.pack(side="right")
        ttk.Label(right, text="搜索:").pack(side="left", padx=(0, 4))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search)
        entry = ttk.Entry(right, textvariable=self.search_var, width=22)
        entry.pack(side="left")
        ttk.Label(right, text="(输入商品名实时筛选)", foreground="gray").pack(side="left", padx=(6, 0))

        # 主体：左分类树 + 右表格
        body = ttk.Frame(self.root, padding=(10, 0))
        body.pack(fill="both", expand=True)

        # 左侧分类
        left = ttk.Frame(body, width=160)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        ttk.Label(left, text="商品分类", font=("Microsoft YaHei", 11, "bold")).pack(anchor="w", pady=(0, 6))

        self.cat_listbox = tk.Listbox(left, width=16, height=20, font=("Microsoft YaHei", 10),
                                      activestyle="dotbox", selectbackground="#cce4ff")
        self.cat_listbox.pack(fill="both", expand=True)
        self.cat_listbox.insert("end", "全部商品")
        for c in self.categories:
            self.cat_listbox.insert("end", c["name"])
        self.cat_listbox.selection_set(0)
        self.cat_listbox.bind("<<ListboxSelect>>", self._on_cat_select)

        # 右侧表格
        right_area = ttk.Frame(body)
        right_area.pack(side="left", fill="both", expand=True, padx=(10, 0))

        columns = ("check", "name", "spec", "unit", "price", "qty", "subtotal")
        self.tree = ttk.Treeview(right_area, columns=columns, show="headings", height=18)

        self.tree.heading("check", text="选")
        self.tree.heading("name", text="商品名称")
        self.tree.heading("spec", text="规格")
        self.tree.heading("unit", text="单位")
        self.tree.heading("price", text="单价(¥)")
        self.tree.heading("qty", text="数量")
        self.tree.heading("subtotal", text="小计(¥)")

        self.tree.column("check", width=40, anchor="center", stretch=False)
        self.tree.column("name", width=200, anchor="w")
        self.tree.column("spec", width=90, anchor="center")
        self.tree.column("unit", width=60, anchor="center")
        self.tree.column("price", width=90, anchor="e")
        self.tree.column("qty", width=80, anchor="center")
        self.tree.column("subtotal", width=100, anchor="e")

        # 行标签交替色
        self.tree.tag_configure("odd", background="#f7f9fc")
        self.tree.tag_configure("even", background="#ffffff")
        self.tree.tag_configure("checked", background="#e8f5e9")

        vsb = ttk.Scrollbar(right_area, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # 点击勾选 / 双击编辑数量
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.bind("<Double-1>", self._on_double_click)

        # 底部：统计 + 操作按钮
        bottom = ttk.Frame(self.root, padding=(10, 8))
        bottom.pack(fill="x")

        self.summary_var = tk.StringVar(value="已选: 0种  合计: ¥0.00")
        ttk.Label(bottom, textvariable=self.summary_var, font=("Microsoft YaHei", 12, "bold"),
                  foreground="#c0392b").pack(side="left")

        btns = ttk.Frame(bottom)
        btns.pack(side="right")
        ttk.Button(btns, text="➕ 新增商品", command=self._add_product).pack(side="left", padx=2)
        ttk.Button(btns, text="🗑 删除商品", command=self._delete_product).pack(side="left", padx=2)
        ttk.Label(btns, text="|", foreground="gray").pack(side="left", padx=4)
        ttk.Button(btns, text="全选", command=self._select_all).pack(side="left", padx=2)
        ttk.Button(btns, text="清空", command=self._clear_all).pack(side="left", padx=2)
        ttk.Button(btns, text="导出CSV", command=self._export_csv).pack(side="left", padx=2)
        ttk.Button(btns, text="打印清单", command=self._print_list).pack(side="left", padx=2)
        ttk.Button(btns, text="复制摘要", command=self._copy_summary).pack(side="left", padx=2)

        # 数据行编辑浮层（数量输入）
        self._qty_entry = None

    # --------------------------------------------------------
    # 筛选 & 刷新表格
    # --------------------------------------------------------
    def _get_filtered(self):
        """返回当前筛选条件下的商品列表（引用 self.all_items 中的对象）"""
        result = []
        kw = self.search_kw.strip().lower()
        for item in self.all_items:
            if self.current_cat != "全部商品" and item["cat"] != self.current_cat:
                continue
            if kw and kw not in item["name"].lower():
                continue
            result.append(item)
        return result

    def _refresh_table(self):
        """根据当前筛选刷新表格"""
        # 清空
        for iid in self.tree.get_children():
            self.tree.delete(iid)

        items = self._get_filtered()
        for i, item in enumerate(items):
            check_mark = "☑" if item["checked"] else "☐"
            subtotal = item["price"] * item["qty"] if item["qty"] > 0 else 0
            tag = "checked" if item["checked"] else ("odd" if i % 2 else "even")
            self.tree.insert("end", iid=str(id(item)), values=(
                check_mark,
                item["name"],
                item["spec"],
                item["unit"],
                f"{item['price']:.2f}",
                str(item["qty"]) if item["qty"] > 0 else "",
                f"{subtotal:.2f}" if subtotal > 0 else "",
            ), tags=(tag,))

        self._update_summary()

    def _on_search(self, *_):
        self.search_kw = self.search_var.get()
        self._refresh_table()

    def _on_cat_select(self, _):
        sel = self.cat_listbox.curselection()
        if not sel:
            return
        self.current_cat = self.cat_listbox.get(sel[0])
        self._refresh_table()

    # --------------------------------------------------------
    # 勾选 & 数量编辑
    # --------------------------------------------------------
    def _on_click(self, event):
        """单击第一列(选)切换勾选"""
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        if col != "#1":  # 第一列才是勾选
            return
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        # 找到对应 item
        item = self._find_item_by_iid(row_id)
        if item:
            item["checked"] = not item["checked"]
            if not item["checked"]:
                item["qty"] = 0
            self._refresh_table()

    def _on_double_click(self, event):
        """双击数量列进入编辑"""
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        if col != "#6":  # 数量列
            return
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        item = self._find_item_by_iid(row_id)
        if not item:
            return
        # 自动勾选
        item["checked"] = True
        self._edit_qty(row_id, item)

    def _find_item_by_iid(self, iid):
        for item in self.all_items:
            if str(id(item)) == iid:
                return item
        return None

    def _edit_qty(self, row_id, item):
        """在数量列位置弹出输入框"""
        # 先关闭已有输入框
        if self._qty_entry:
            self._qty_entry.destroy()
            self._qty_entry = None

        # 获取单元格位置
        x, y, w, h = self.tree.bbox(row_id, "qty")
        if not w:
            return

        var = tk.StringVar(value=str(item["qty"]) if item["qty"] > 0 else "")
        entry = ttk.Entry(self.tree, textvariable=var, width=8, justify="center")
        entry.place(x=x, y=y, width=w, height=h)
        entry.focus_set()
        entry.select_range(0, "end")
        self._qty_entry = entry

        def commit(_=None):
            raw = var.get().strip()
            try:
                val = int(float(raw))  # 允许输入 3.0 之类
                if val < 0:
                    val = 0
            except ValueError:
                val = 0
            item["qty"] = val
            if val > 0:
                item["checked"] = True
            elif item["checked"] and val == 0:
                pass  # 保留勾选但数量0
            entry.destroy()
            self._qty_entry = None
            self._refresh_table()

        def cancel(_=None):
            entry.destroy()
            self._qty_entry = None

        entry.bind("<Return>", commit)
        entry.bind("<Escape>", cancel)
        entry.bind("<FocusOut>", commit)

    # --------------------------------------------------------
    # 统计
    # --------------------------------------------------------
    def _update_summary(self):
        count = 0
        total = 0.0
        total_qty = 0
        for item in self.all_items:
            if item["checked"] and item["qty"] > 0:
                count += 1
                total += item["price"] * item["qty"]
                total_qty += item["qty"]
        self.summary_var.set(f"已选: {count}种  共{total_qty}{self._common_unit()}  合计: ¥{total:.2f}")

    def _common_unit(self):
        return "件"

    def _get_selected_items(self):
        """返回已勾选且数量>0 的商品列表"""
        return [item for item in self.all_items if item["checked"] and item["qty"] > 0]

    # --------------------------------------------------------
    # 批量操作
    # --------------------------------------------------------
    def _select_all(self):
        for item in self._get_filtered():
            item["checked"] = True
            if item["qty"] == 0:
                item["qty"] = 1
        self._refresh_table()

    def _clear_all(self):
        for item in self.all_items:
            item["checked"] = False
            item["qty"] = 0
        self._refresh_table()

    # --------------------------------------------------------
    # 导出 CSV
    # --------------------------------------------------------
    def _export_csv(self):
        selected = self._get_selected_items()
        if not selected:
            messagebox.showinfo("提示", "请先勾选商品并输入数量。")
            return

        default_name = f"看货清单_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path = filedialog.asksaveasfilename(
            title="导出CSV",
            defaultextension=".csv",
            filetypes=[("CSV文件", "*.csv")],
            initialfile=default_name,
        )
        if not path:
            return

        # 用 UTF-8 BOM 让 Excel 正确识别中文
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([self.shop_name])
            writer.writerow([f"日期: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"])
            writer.writerow([])
            writer.writerow(["分类", "商品名称", "规格", "单位", "单价", "数量", "小计"])
            total = 0.0
            for item in selected:
                subtotal = item["price"] * item["qty"]
                total += subtotal
                writer.writerow([
                    item["cat"], item["name"], item["spec"], item["unit"],
                    f"{item['price']:.2f}", item["qty"], f"{subtotal:.2f}"
                ])
            writer.writerow([])
            writer.writerow(["", "", "", "", "", "合计", f"{total:.2f}"])

        messagebox.showinfo("成功", f"已导出到:\n{path}")

    # --------------------------------------------------------
    # 打印清单
    # --------------------------------------------------------
    def _print_list(self):
        selected = self._get_selected_items()
        if not selected:
            messagebox.showinfo("提示", "请先勾选商品并输入数量。")
            return

        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        rows_html = ""
        total = 0.0
        for item in selected:
            subtotal = item["price"] * item["qty"]
            total += subtotal
            rows_html += (
                f"<tr>"
                f"<td>{self._esc(item['cat'])}</td>"
                f"<td class='name'>{self._esc(item['name'])}</td>"
                f"<td>{self._esc(item['spec'])}</td>"
                f"<td>{self._esc(item['unit'])}</td>"
                f"<td class='num'>{item['price']:.2f}</td>"
                f"<td class='num'>{item['qty']}</td>"
                f"<td class='num'>{subtotal:.2f}</td>"
                f"</tr>"
            )

        html = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>{self._esc(self.shop_name)} - 看货清单</title>
<style>
  body {{ font-family: "Microsoft YaHei", sans-serif; margin: 30px; color: #333; }}
  h1 {{ text-align: center; font-size: 22px; margin-bottom: 4px; }}
  .date {{ text-align: center; color: #666; margin-bottom: 20px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: center; }}
  th {{ background: #f0f0f0; font-weight: bold; }}
  td.name {{ text-align: left; }}
  td.num {{ text-align: right; }}
  tfoot td {{ font-weight: bold; font-size: 16px; background: #fffde7; }}
  .total-row td {{ border-top: 2px solid #333; }}
</style></head>
<body>
  <h1>{self._esc(self.shop_name)}</h1>
  <div class="date">看货清单 — {now}</div>
  <table>
    <thead>
      <tr><th>分类</th><th>商品名称</th><th>规格</th><th>单位</th><th>单价¥</th><th>数量</th><th>小计¥</th></tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
    <tfoot>
      <tr class="total-row"><td colspan="6" style="text-align:right;">合计</td><td class="num">¥{total:.2f}</td></tr>
    </tfoot>
  </table>
  <script>window.onload = function(){{ window.print(); }}</script>
</body></html>"""

        # 写入临时 HTML 并打开浏览器
        fd, tmp_path = tempfile.mkstemp(suffix=".html", prefix="kanhuo_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(html)
        webbrowser.open("file://" + tmp_path)

    # --------------------------------------------------------
    # 复制摘要（方便微信发送）
    # --------------------------------------------------------
    def _copy_summary(self):
        selected = self._get_selected_items()
        if not selected:
            messagebox.showinfo("提示", "请先勾选商品并输入数量。")
            return

        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [f"【{self.shop_name}】看货清单", f"日期: {now}", ""]
        total = 0.0
        for item in selected:
            subtotal = item["price"] * item["qty"]
            total += subtotal
            lines.append(f"· {item['name']} {item['spec']} × {item['qty']}{item['unit']} = ¥{subtotal:.2f}")
        lines.append("")
        lines.append(f"合计: ¥{total:.2f}")

        text = "\n".join(lines)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("已复制", "清单摘要已复制到剪贴板，可直接粘贴到微信发送。")

    # --------------------------------------------------------
    # 新增 / 删除商品
    # --------------------------------------------------------
    def _add_product(self):
        """打开新增商品对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("新增商品")
        dialog.geometry("420x340")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        # 居中
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 420) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 340) // 2
        dialog.geometry(f"+{x}+{y}")

        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="新增商品", font=("Microsoft YaHei", 13, "bold")).grid(row=0, column=0, columnspan=2, pady=(0, 12))

        # 分类：下拉选择已有分类 或 输入新分类
        ttk.Label(frame, text="分类:").grid(row=1, column=0, sticky="e", pady=4, padx=(0, 8))
        cat_values = [c["name"] for c in self.categories] + ["+ 新建分类..."]
        cat_var = tk.StringVar()
        cat_combo = ttk.Combobox(frame, textvariable=cat_var, values=cat_values, width=22, state="readonly")
        if self.categories:
            cat_combo.set(self.categories[0]["name"])
        else:
            cat_combo.set("+ 新建分类...")
        cat_combo.grid(row=1, column=1, pady=4)

        new_cat_entry = None

        def on_cat_change(_=None):
            nonlocal new_cat_entry
            if cat_var.get() == "+ 新建分类...":
                if new_cat_entry is None:
                    new_cat_entry = ttk.Entry(frame, width=24)
                    new_cat_entry.grid(row=2, column=1, pady=2)
                    new_cat_entry.focus_set()
            else:
                if new_cat_entry:
                    new_cat_entry.destroy()
                    new_cat_entry = None

        cat_combo.bind("<<ComboboxSelected>>", on_cat_change)

        # 商品名称
        ttk.Label(frame, text="商品名称 *:").grid(row=3, column=0, sticky="e", pady=4, padx=(0, 8))
        name_var = tk.StringVar()
        ttk.Entry(frame, textvariable=name_var, width=24).grid(row=3, column=1, pady=4)

        # 规格
        ttk.Label(frame, text="规格:").grid(row=4, column=0, sticky="e", pady=4, padx=(0, 8))
        spec_var = tk.StringVar()
        ttk.Entry(frame, textvariable=spec_var, width=24).grid(row=4, column=1, pady=4)

        # 单位
        ttk.Label(frame, text="单位:").grid(row=5, column=0, sticky="e", pady=4, padx=(0, 8))
        unit_var = tk.StringVar()
        ttk.Entry(frame, textvariable=unit_var, width=24).grid(row=5, column=1, pady=4)

        # 单价
        ttk.Label(frame, text="单价(¥) *:").grid(row=6, column=0, sticky="e", pady=4, padx=(0, 8))
        price_var = tk.StringVar()
        ttk.Entry(frame, textvariable=price_var, width=24).grid(row=6, column=1, pady=4)

        def do_add():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("提示", "请输入商品名称。", parent=dialog)
                return
            price_raw = price_var.get().strip()
            if not price_raw:
                messagebox.showwarning("提示", "请输入单价。", parent=dialog)
                return
            try:
                price = float(price_raw)
                if price < 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("提示", "单价请输入有效的数字。", parent=dialog)
                return

            # 确定分类
            if cat_var.get() == "+ 新建分类...":
                if not new_cat_entry or not new_cat_entry.get().strip():
                    messagebox.showwarning("提示", "请输入新分类名称。", parent=dialog)
                    return
                cat_name = new_cat_entry.get().strip()
            else:
                cat_name = cat_var.get()

            spec = spec_var.get().strip()
            unit = unit_var.get().strip() or "件"

            # 添加到数据结构
            self._do_add_item(cat_name, name, spec, unit, price)
            messagebox.showinfo("成功", f"已添加: {name}", parent=dialog)
            dialog.destroy()

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=7, column=0, columnspan=2, pady=(16, 0))
        ttk.Button(btn_frame, text="添加", command=do_add).pack(side="left", padx=8)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side="left", padx=8)

        # 回车提交
        name_var.trace_add("write", lambda *_: None)
        dialog.bind("<Return>", lambda _: do_add())

    def _do_add_item(self, cat_name, name, spec, unit, price):
        """将新商品加入内存数据 + 保存到JSON + 刷新界面"""
        # 找到或创建分类
        cat = None
        for c in self.categories:
            if c["name"] == cat_name:
                cat = c
                break
        if cat is None:
            cat = {"name": cat_name, "products": []}
            self.categories.append(cat)

        product = {"name": name, "spec": spec, "unit": unit, "price": price}
        cat["products"].append(product)

        # 加入扁平列表
        self.all_items.append({
            "cat": cat_name,
            "name": name,
            "spec": spec,
            "unit": unit,
            "price": price,
            "qty": 0,
            "checked": False,
        })

        # 保存到JSON
        self._save_to_json()

        # 刷新分类列表
        self._rebuild_cat_list()

        # 刷新表格（切到新分类）
        self.current_cat = cat_name
        self.cat_listbox.selection_clear(0, "end")
        for i in range(self.cat_listbox.size()):
            if self.cat_listbox.get(i) == cat_name:
                self.cat_listbox.selection_set(i)
                break
        self._refresh_table()

    def _delete_product(self):
        """删除选中的商品行"""
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在表格中选中要删除的商品行（点击行任意位置）。")
            return

        row_id = sel[0]
        item = self._find_item_by_iid(row_id)
        if not item:
            return

        if not messagebox.askyesno("确认删除", f"确定要删除商品「{item['name']}」吗？\n此操作不可撤销。"):
            return

        # 从内存删除
        self.all_items.remove(item)

        # 从 categories 删除
        for cat in self.categories:
            if cat["name"] == item["cat"]:
                cat["products"] = [p for p in cat["products"] if not (
                    p["name"] == item["name"] and
                    p.get("spec", "") == item["spec"] and
                    p.get("unit", "") == item["unit"] and
                    float(p.get("price", 0)) == item["price"]
                )]
                # 如果分类空了，删除分类
                if not cat["products"]:
                    self.categories.remove(cat)
                break

        # 保存
        self._save_to_json()
        self._rebuild_cat_list()
        self._refresh_table()
        messagebox.showinfo("已删除", f"已删除商品「{item['name']}」")

    def _save_to_json(self):
        """将当前内存中的数据保存回 products.json"""
        data = {"shop_name": self.shop_name, "categories": self.categories}
        save_data(data)

    def _rebuild_cat_list(self):
        """重建左侧分类列表"""
        self.cat_listbox.delete(0, "end")
        self.cat_listbox.insert("end", "全部商品")
        for c in self.categories:
            self.cat_listbox.insert("end", c["name"])
        self.cat_listbox.selection_set(0)
        self.current_cat = "全部商品"

    # --------------------------------------------------------
    # 工具
    # --------------------------------------------------------
    @staticmethod
    def _esc(s):
        return (str(s).replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


# ============================================================
# 启动
# ============================================================

def main():
    root = tk.Tk()
    # 设置整体风格
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("Treeview", rowheight=28, font=("Microsoft YaHei", 10))
    style.configure("Treeview.Heading", font=("Microsoft YaHei", 10, "bold"))

    app = ProductViewerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
