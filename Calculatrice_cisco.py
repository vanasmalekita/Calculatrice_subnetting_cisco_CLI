import ipaddress, csv, json, sys
from rich.console import Console
from rich.table import Table
from rich.prompt import IntPrompt, Prompt

console = Console()

class NetworkPlanner:
    def __init__(self):
        self.network = None
        self.routers = []

    def gather_input(self):
        while True:
            try:
                net_input = Prompt.ask("Adresse réseau principale (ex: 192.168.0.0/16)")
                self.network = ipaddress.IPv4Network(net_input, strict=False)
                break
            except ValueError:
                console.print("[red]Adresse invalide.[/red]")

        nb_routers = IntPrompt.ask("Nombre de routeurs", default=2)
        for r in range(1, nb_routers + 1):
            console.print(f"\n[bold cyan]Routeur R{r}[/bold cyan]")
            interfaces = IntPrompt.ask("  Nombre d'interfaces connectées (hors loopback)", default=2)
            subnets = IntPrompt.ask("  Nombre de sous-réseaux connectés", default=1)

            router = {"name": f"R{r}", "interfaces": interfaces, "subnets": []}
            for s in range(1, subnets + 1):
                hosts = IntPrompt.ask(f"    Sous-réseau {s} - Nombre d'utilisateurs", default=10)
                router["subnets"].append({"name": f"LAN{s}", "hosts": hosts})
            self.routers.append(router)

    def check_capacity(self):
        total_needed = 0
        for r in self.routers:
            for s in r["subnets"]:
                needed = s["hosts"] + 2
                total_needed += 2 ** (32 - max(32 - (needed - 1).bit_length(), 24))
        nb_p2p = len(self.routers) * (len(self.routers) - 1) // 2
        total_needed += nb_p2p * 4  # /30 = 4 adresses
        if total_needed > self.network.num_addresses:
            console.print(f"[red]❌ Réseau trop petit ![/red] Besoin de {int(total_needed)} adresses, réseau fourni : {self.network.num_addresses}")
            sys.exit(1)

    def calculate_vlsm(self):
        allocations = []
        remaining = self.network
        all_subnets = []

        # Collecter tous les sous-réseaux (LAN + P2P)
        for r in self.routers:
            for s in r["subnets"]:
                needed = s["hosts"] + 2
                prefix = 32 - (needed - 1).bit_length()
                all_subnets.append({
                    "type": "LAN",
                    "desc": f"{r['name']}-{s['name']}",
                    "hosts": s["hosts"],
                    "prefix": max(prefix, 24)
                })

        # Ajouter les liens point-à-point
        for i in range(len(self.routers)):
            for j in range(i + 1, len(self.routers)):
                all_subnets.append({
                    "type": "P2P",
                    "desc": f"{self.routers[i]['name']}->{self.routers[j]['name']}",
                    "hosts": 2,
                    "prefix": 30
                })

        # Trier du plus grand au plus petit (VLSM)
        all_subnets.sort(key=lambda x: (1_000_000 if x["type"] == "P2P" else -x["hosts"]))

        # Allocation
        for item in all_subnets:
            try:
                subnet = list(remaining.subnets(new_prefix=item["prefix"]))[0]
            except IndexError:
                console.print(f"[red]❌ Impossible d'allouer {item['desc']} : plus d'espace.[/red]")
                continue

            allocations.append({
                "type": item["type"],
                "desc": item["desc"],
                "network": str(subnet),
                "mask": str(subnet.netmask),
                "range": f"{subnet.network_address + 1} - {subnet.broadcast_address - 1}",
                "broadcast": str(subnet.broadcast_address)
            })

            remaining_parts = list(remaining.address_exclude(subnet))
            remaining = remaining_parts[0] if remaining_parts else None
            if remaining is None:
                console.print("[red]⚠️ Espace réseau épuisé.[/red]")
                break

        return allocations

    def display_table(self, allocations):
        table = Table(title="Plan d'adressage IP")
        table.add_column("Type", style="cyan")
        table.add_column("Description", style="magenta")
        table.add_column("Réseau", style="green")
        table.add_column("Masque", style="yellow")
        table.add_column("Plage utilisable", style="blue")
        table.add_column("Broadcast", style="red")

        for a in allocations:
            table.add_row(
                a["type"], a["desc"], a["network"],
                a["mask"], a["range"], a["broadcast"]
            )
        console.print(table)

    def export_json(self, allocations, filename="plan.json"):
        with open(filename, 'w') as f:
            json.dump(allocations, f, indent=2)
        console.print(f"[green]✅ Export JSON réussi : {filename}[/green]")

    def export_csv(self, allocations, filename="plan.csv"):
        with open(filename, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=allocations[0].keys())
            writer.writeheader()
            writer.writerows(allocations)
        console.print(f"[green]✅ Export CSV réussi : {filename}[/green]")

    def run(self):
        self.gather_input()
        self.check_capacity()
        allocations = self.calculate_vlsm()
        self.display_table(allocations)

        export_choice = Prompt.ask("\nExporter les résultats ?", choices=["json", "csv", "non"], default="non")
        if export_choice == "json":
            self.export_json(allocations)
        elif Prompt.ask("Exporter en CSV ?", choices=["oui", "non"], default="non") == "oui":
            self.export_csv(allocations)

if __name__ == "__main__":
    try:
        planner = NetworkPlanner()
        planner.run()
    except KeyboardInterrupt:
        console.print("\n[red]Interrompu par l'utilisateur.[/red]")
        sys.exit(0)
