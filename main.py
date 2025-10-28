import requests
import pandas as pd
import time
import os
import json
from tqdm import tqdm
from datetime import datetime

# Konfigurasi
API_BASE = "https://api-sekolah-indonesia.vercel.app/sekolah"
PER_PAGE = 100  # Maksimal data per request
OUTPUT_FILE = "data_sekolah_indonesia.csv"
CHECKPOINT_FILE = "scraping_checkpoint.json"
TEMP_DATA_FILE = "temp_scraped_data.csv"

def save_checkpoint(page, total_pages, data_count):
    """Simpan checkpoint progress"""
    checkpoint = {
        'last_page': page,
        'total_pages': total_pages,
        'data_count': data_count,
        'timestamp': datetime.now().isoformat()
    }
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump(checkpoint, f)

def load_checkpoint():
    """Load checkpoint jika ada"""
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, 'r') as f:
                return json.load(f)
        except:
            return None
    return None

def load_existing_data():
    """Load data yang sudah di-scrape sebelumnya"""
    if os.path.exists(TEMP_DATA_FILE):
        try:
            df = pd.read_csv(TEMP_DATA_FILE, encoding='utf-8-sig')
            return df.to_dict('records')
        except:
            return []
    return []

def save_temp_data(all_data):
    """Simpan data sementara"""
    df = pd.DataFrame(all_data)
    df.to_csv(TEMP_DATA_FILE, index=False, encoding='utf-8-sig')

def get_total_data():
    """Mendapatkan total jumlah data"""
    try:
        response = requests.get(f"{API_BASE}?page=1&perPage=1", timeout=30)
        data = response.json()
        return data.get('total_data', 0)
    except Exception as e:
        print(f"Error mendapatkan total data: {e}")
        return 0

def scrape_sekolah_page(page, per_page, max_retries=3):
    """Scraping data sekolah per halaman dengan retry"""
    for attempt in range(max_retries):
        try:
            params = {
                'page': page,
                'perPage': per_page
            }
            response = requests.get(API_BASE, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('dataSekolah', [])
            else:
                print(f"\nStatus code {response.status_code} pada halaman {page}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
        except Exception as e:
            print(f"\nError halaman {page} (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
    
    return []

def scrape_all_sekolah(resume=True):
    """Scraping semua data sekolah dengan resume capability"""
    print("Memulai scraping data sekolah Indonesia...")
    
    # Cek checkpoint
    checkpoint = load_checkpoint() if resume else None
    start_page = 1
    all_data = []
    
    if checkpoint and resume:
        print(f"\nCheckpoint ditemukan!")
        print(f"   Last page: {checkpoint['last_page']}")
        print(f"   Data tersimpan: {checkpoint['data_count']:,}")
        print(f"   Timestamp: {checkpoint['timestamp']}")
        
        response = input("\nResume dari checkpoint? (y/n): ").lower()
        if response == 'y':
            start_page = checkpoint['last_page'] + 1
            all_data = load_existing_data()
            print(f"Melanjutkan dari halaman {start_page}")
            print(f"Data yang sudah tersimpan: {len(all_data):,}")
        else:
            print("Memulai scraping dari awal...")
            if os.path.exists(TEMP_DATA_FILE):
                os.remove(TEMP_DATA_FILE)
            if os.path.exists(CHECKPOINT_FILE):
                os.remove(CHECKPOINT_FILE)
    
    # Get total data
    total_data = get_total_data()
    print(f"\nTotal data yang akan di-scrape: {total_data:,} sekolah")
    
    if total_data == 0:
        print("Tidak dapat mengambil informasi total data")
        return
    
    # Hitung total halaman
    total_pages = (total_data // PER_PAGE) + (1 if total_data % PER_PAGE > 0 else 0)
    print(f"Total halaman: {total_pages:,} halaman")
    print(f"Mulai dari halaman: {start_page}")
    
    # Progress bar
    total_to_scrape = total_pages - start_page + 1
    with tqdm(total=total_to_scrape, desc="Scraping Progress", initial=0) as pbar:
        for page in range(start_page, total_pages + 1):
            # Scrape data
            sekolah_list = scrape_sekolah_page(page, PER_PAGE)
            
            if sekolah_list:
                all_data.extend(sekolah_list)
                pbar.update(1)
                pbar.set_postfix({
                    'Data': f"{len(all_data):,}/{total_data:,}",
                    'Page': f"{page}/{total_pages}"
                })
                
                # Save checkpoint setiap 10 halaman
                if page % 10 == 0:
                    save_checkpoint(page, total_pages, len(all_data))
                    save_temp_data(all_data)
                
                # Save checkpoint besar setiap 100 halaman
                if page % 100 == 0:
                    backup_file = f"backup_page_{page}.csv"
                    df_backup = pd.DataFrame(all_data)
                    df_backup.to_csv(backup_file, index=False, encoding='utf-8-sig')
                    print(f"\nBackup disimpan: {backup_file}")
            else:
                print(f"\nGagal mengambil data halaman {page} setelah beberapa retry")
            
            # Delay untuk menghindari rate limit
            time.sleep(0.5)
    
    print(f"\nScraping selesai! Total data: {len(all_data):,}")
    
    # Convert ke DataFrame
    df = pd.DataFrame(all_data)
    
    # Hapus duplikat berdasarkan NPSN
    initial_count = len(df)
    df = df.drop_duplicates(subset=['npsn'], keep='first')
    if initial_count > len(df):
        print(f"Menghapus {initial_count - len(df):,} data duplikat")
    
    # Reorder kolom (opsional)
    column_order = [
        'npsn', 'sekolah', 'bentuk', 'status',
        'alamat_jalan', 'kecamatan', 'kabupaten_kota', 'propinsi',
        'kode_kec', 'kode_kab_kota', 'kode_prop',
        'lintang', 'bujur', 'id'
    ]
    
    # Pastikan semua kolom ada
    existing_columns = [col for col in column_order if col in df.columns]
    df = df[existing_columns]
    
    # Save ke CSV final
    df.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')
    print(f"Data berhasil disimpan ke: {OUTPUT_FILE}")
    
    # Clean up temporary files
    if os.path.exists(TEMP_DATA_FILE):
        os.remove(TEMP_DATA_FILE)
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)
    print("File temporary dibersihkan")
    
    # Statistik
    print("\n" + "="*60)
    print("STATISTIK DATA")
    print("="*60)
    print(f"Total Sekolah: {len(df):,}")
    print(f"Total Kolom: {len(df.columns)}")
    
    if 'bentuk' in df.columns:
        print("\nDistribusi Jenjang:")
        for jenjang, count in df['bentuk'].value_counts().items():
            percentage = (count / len(df)) * 100
            print(f"   {jenjang:5} : {count:7,} sekolah ({percentage:5.2f}%)")
    
    if 'status' in df.columns:
        print("\nDistribusi Status:")
        for status, count in df['status'].value_counts().items():
            status_name = "Negeri" if status == "N" else "Swasta"
            percentage = (count / len(df)) * 100
            print(f"   {status_name:7} : {count:7,} sekolah ({percentage:5.2f}%)")
    
    if 'propinsi' in df.columns:
        print("\nTop 10 Provinsi:")
        top_provinces = df['propinsi'].value_counts().head(10)
        for i, (prov, count) in enumerate(top_provinces.items(), 1):
            print(f"   {i:2}. {prov:30} : {count:6,} sekolah")
    
    print("\n" + "="*60)

def main():
    """Main function"""
    print("=" * 60)
    print("  SCRAPER DATA SEKOLAH SELURUH INDONESIA v2.0")
    print("  Dengan Resume Capability")
    print("=" * 60)
    
    try:
        scrape_all_sekolah(resume=True)
        print("\nProses selesai!")
    except KeyboardInterrupt:
        print("\n\nProses dihentikan oleh user")
        print("Checkpoint dan data sementara sudah disimpan")
        print("Jalankan kembali script untuk melanjutkan")
    except Exception as e:
        print(f"\nError: {e}")
        print("Checkpoint dan data sementara mungkin sudah disimpan")
        print("Coba jalankan kembali script untuk melanjutkan")

if __name__ == "__main__":
    main()
