import pandas as pd
import numpy as np

input_file = r"C:\Users\sarba\Downloads\prueba mariana.xlsx"

try:
    xl = pd.ExcelFile(input_file)
    df_raw = pd.read_excel(input_file, sheet_name=xl.sheet_names[0])
    numeric_cols = df_raw.select_dtypes(include=[np.number]).columns
    x_col = numeric_cols[0]
    y_cols = [col for col in df_raw.columns if 'Y' in str(col).upper()]
    if len(y_cols) < 3:
        y_cols = numeric_cols[1:4]

    for i in range(min(3, len(y_cols))):
        y_col = y_cols[i]
        df_split = df_raw[[x_col, y_col]].dropna()
        xs = df_split.iloc[:,0].values
        ys = df_split.iloc[:,1].values
        
        n = len(xs)
        if n > 1:
            denom = (n * np.sum(xs**2) - np.sum(xs)**2)
            if denom != 0:
                m = (n * np.sum(xs * ys) - np.sum(xs) * np.sum(ys)) / denom
                b = (np.sum(ys) - m * np.sum(xs)) / n
                print(f"Y{i+1} ({y_col}): y = {m:.4f}x + {b:.4f}")
            else:
                print(f"Y{i+1}: No calculable (X constante)")
        else:
            print(f"Y{i+1}: Datos insuficientes")

except Exception as e:
    print(f"ERROR: {e}")
