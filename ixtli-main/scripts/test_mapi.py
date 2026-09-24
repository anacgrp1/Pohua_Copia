import win32com.client
import time

def test():
    outlook = win32com.client.Dispatch("Outlook.Application")
    namespace = outlook.GetNamespace("MAPI")
    
    for f_id in [6, 5, 3]:
        folder = namespace.GetDefaultFolder(f_id)
        print(f"\nCarpeta: {folder.Name}")
        
        t0 = time.time()
        sub_count = folder.Folders.Count
        print(f"folder.Folders.Count tomó {time.time() - t0:.2f}s, total: {sub_count}")
        
        for i in range(1, min(sub_count + 1, 10)):
            sub = folder.Folders.Item(i)
            print(f"  Subcarpeta: {sub.Name}, items: {sub.Items.Count}")

test()
