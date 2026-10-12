from __future__ import annotations

import docker


def discover_docker_images() -> list[dict]:
    client = docker.from_env()
    images = []
    for img in client.images.list():
        images.append({
            "id": img.short_id,
            "tags": img.tags,
            "size_mb": round(img.attrs.get("Size", 0) / (1024 * 1024), 1),
        })
    return images


def discover_docker_containers() -> list[dict]:
    client = docker.from_env()
    containers = []
    for c in client.containers.list(all=True):
        image_tags = c.image.tags if c.image else []
        containers.append({
            "id": c.short_id,
            "name": c.name,
            "image": image_tags[0] if image_tags else (c.image.short_id if c.image else "unknown"),
            "status": c.status,
        })
    return containers


if __name__ == "__main__":
    print("Docker images:")
    for img in discover_docker_images():
        print(f"  {img['id']}  {img['tags']}  {img['size_mb']} MB")

    print("\nDocker containers:")
    for c in discover_docker_containers():
        print(f"  {c['name']}  image={c['image']}  status={c['status']}")