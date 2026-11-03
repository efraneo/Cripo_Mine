import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from openpyxl import Workbook
from openpyxl.drawing.image import Image
import os

# Paths
input_file = r"C:\Users\sarba\Downloads\prueba mariana.xlsx"
output_file = r"C:\Users\sarba\Downloads\resultado_analisis_mariana.xlsx"

try:
    # Load the file
    xl = pd.ExcelFile(input_file)
    sheet_name = xl.sheet_names[0] 
    df_raw = pd.read_excel(input_file, sheet_name=sheet_name)
    
    # Identify X column (first numeric)
    numeric_cols = df_raw.select_dtypes(include=[np.number]).columns
    if len(numeric_cols) < 2:
        raise ValueError("No hay suficientes columnas numéricas.")
        
    x_col = numeric_cols[0]
    
    # Identify Y columns (Y1, Y2, Y3)
    y_cols = [col for col in df_raw.columns if 'Y' in str(col).upper()]
    if len(y_cols) < 3:
        y_cols = numeric_cols[1:4]

    # Global Regression
    all_data = []
    for idx, row in df_raw.iterrows():
        x_val = row[x_col]
        for y_col in y_cols:
            y_val = row[y_col]
            if pd.notnull(x_val) and pd.notnull(y_val):
                all_data.append([x_val, y_val])
    
    df_all = pd.DataFrame(all_data, columns=['X', 'Y'])
    x_all = df_all['X'].values
    y_all = df_all['Y'].values
    
    n_all = len(x_all)
    m_all = (n_all * np.sum(x_all * y_all) - np.sum(x_all) * np.sum(y_all)) / (n_all * np.sum(x_all**2) - np.sum(x_all)**2)
    b_all = (np.sum(y_all) - m_all * np.sum(x_all)) / n_all
    eq_all = f"y = {m_all:.4f}x + {b_all:.4f}"

    # PRE-GENERATE ALL IMAGES
    plt.figure(figsize=(10, 7))
    plt.scatter(x_all, y_all, color='blue', alpha=0.5)
    plt.plot(x_all, m_all*x_all + b_all, color='red', linewidth=2)
    plt.title("Tendencia General Consolidada")
    plt.grid(True)
    plt.savefig("gen_plot.png")
    plt.close()

    plot_paths = []
    for i in range(min(3, len(y_cols))):
        y_col = y_cols[i]
        df_split = df_raw[[x_col, y_col]].dropna()
        xs = df_split.iloc[:,0].values
        ys = df_split.iloc[:,1].values
        
        plt.figure(figsize=(6, 4))
        plt.scatter(xs, ys, color='blue', alpha=0.6)
        
        nn = len(xs)
        if nn > 1:
            denom = (nn * np.sum(xs**2) - np.sum(xs)**2)
            if denom != 0:
                mi = (nn * np.sum(xs * ys) - np.sum(xs) * np.sum(ys)) / denom
                bi = (np.sum(ys) - mi * np.sum(xs)) / nn
                plt.plot(xs, mi*xs + bi, color='red')
        
        plt.title(f"Dispersión X vs {y_col}")
        plt.grid(True)
        path = f"plot_{i+1}.png"
        plt.savefig(path)
        plt.close()
        plot_paths.append(path)

    # SAVE TO EXCEL
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        for i in range(min(3, len(y_cols))):
            y_col = y_cols[i]
            df_split = df_raw[[x_col, y_col]].dropna()
            df_split.columns = ['X', f'Y{i+1}']
            df_split.to_excel(writer, sheet_name=f"Datos{i+1}", index=False)
            
            wb = writer.book
            ws = wb.create_sheet(f"grafica{i+1}")
            ws['A1'] = f"ANÁLISIS {y_col}"
            img = Image(plot_paths[i])
            ws.add_image(img, 'B5')

        wb = writer.book
        ws_gen = wb.create_sheet("grafica_general", 0)
        ws_gen['A1'] = "ANÁLISIS GLOBAL (Y1+Y2+Y3)"
        ws_gen['A2'] = f"Ecuación General: {eq_all}"
        img_gen = Image("gen_plot.png")
        ws_gen.add_image(img_gen, 'B6')

    # Cleanup
    for p in plot_paths: os.remove(p)
    os.remove("gen_plot.png")

    print(f"SUCCESS: File saved as {output_file}")

except Exception as e:
    print(f"ERROR: {e}")
