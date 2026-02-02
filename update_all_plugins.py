#!/usr/bin/env python3
"""
Script per workflow GitHub - Aggiorna traduzioni di tutti i plugin
"""
import os
import sys
import subprocess
import json


def find_translation_scripts():
    """Trova tutti gli script update_translations.py"""
    scripts = []

    for root, dirs, files in os.walk("."):
        if ".git" in root:
            continue

        for file in files:
            if file == "update_translations.py":
                script_path = os.path.join(root, file)
                scripts.append({
                    "path": script_path,
                    "plugin_dir": os.path.dirname(script_path),
                    "plugin_name": os.path.basename(os.path.dirname(script_path))
                })

    return scripts


def run_translation_update(script_info):
    """Esegue lo script di aggiornamento traduzioni"""
    plugin_dir = script_info["plugin_dir"]
    print(f"\n{'=' * 60}")
    print(f"🔄 Processing: {script_info['plugin_name']}")
    print(f"📁 Directory: {plugin_dir}")
    print(f"{'=' * 60}")

    try:
        # Cambia directory
        original_dir = os.getcwd()
        os.chdir(plugin_dir)

        # Esegui lo script
        result = subprocess.run(
            [sys.executable, "update_translations.py"],
            capture_output=True,
            text=True
        )

        # Torna alla directory originale
        os.chdir(original_dir)

        return {
            "plugin": script_info["plugin_name"],
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }

    except Exception as e:
        return {
            "plugin": script_info["plugin_name"],
            "success": False,
            "error": str(e)
        }


def main():

    """Funzione principale"""
    print("🚀 Starting automatic translation updates for all plugins")

    # Trova tutti gli script
    scripts = find_translation_scripts()

    if not scripts:
        print("❌ No update_translations.py scripts found")
        return 1

    print(f"📦 Found {len(scripts)} plugins with translation scripts")

    # Esegui aggiornamenti
    results = []
    for script in scripts:
        result = run_translation_update(script)
        results.append(result)

        if result["success"]:
            print(f"✅ {script['plugin_name']}: Success")
        else:
            print(f"❌ {script['plugin_name']}: Failed")
            if "error" in result:
                print(f"   Error: {result['error']}")

    # Genera report
    successful = sum(1 for r in results if r["success"])
    failed = len(results) - successful

    print(f"\n{'=' * 60}")
    print("📊 FINAL REPORT")
    print(f"{'=' * 60}")
    print(f"Total plugins: {len(results)}")
    print(f"✅ Successful: {successful}")
    print(f"❌ Failed: {failed}")

    # Salva report JSON per il workflow
    report = {
        "timestamp": subprocess.check_output(["date", "-Iseconds"]).decode().strip(),
        "total_plugins": len(results),
        "successful": successful,
        "failed": failed,
        "details": results
    }

    with open("translation_update_report.json", "w") as f:
        json.dump(report, f, indent=2)

    print("\n📄 Report saved to: translation_update_report.json")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
