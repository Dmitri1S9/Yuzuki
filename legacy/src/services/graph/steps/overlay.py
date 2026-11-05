"""Post-processes a rendered pyvis HTML file to draw large-group bounding
boxes on top of the force layout — pyvis itself has no concept of a
region enclosing a set of nodes, so this injects a small script that
computes and draws one after the physics layout settles.
"""
import json


def inject_large_group_areas(out_path: str, large_groups: dict[str, set[str]],
                              area_colors: dict[str, str]) -> None:
    with open(out_path, encoding="utf-8") as f:
        html = f.read()

    groups_json = json.dumps({name: sorted(members) for name, members in large_groups.items()})
    colors_json = json.dumps(area_colors)

    extra = f"""
<script type="text/javascript">
window.addEventListener("load", function() {{
  var largeGroups = {groups_json};
  var largeColors = {colors_json};
  var names = Object.keys(largeGroups);
  var basePad = 45;

  function calcBox(ids, pad) {{
    var positions = network.getPositions(ids);
    var xs = [], ys = [];
    ids.forEach(function(id) {{
      if (positions[id]) {{ xs.push(positions[id].x); ys.push(positions[id].y); }}
    }});
    if (xs.length === 0) return null;
    return {{
      minX: Math.min.apply(null, xs) - pad, maxX: Math.max.apply(null, xs) + pad,
      minY: Math.min.apply(null, ys) - pad, maxY: Math.max.apply(null, ys) + pad,
    }};
  }}

  function overlaps(a, b) {{
    return a.minX < b.maxX && a.maxX > b.minX && a.minY < b.maxY && a.maxY > b.minY;
  }}

  network.on("beforeDrawing", function(ctx) {{
    // Areas must never visually overlap. Large groups are normally disjoint
    // (a character belongs to one side), but if physics ever puts two boxes
    // in conflict, shrink both together until they clear, down to a floor —
    // never draw two overlapping filled regions.
    var pad = basePad;
    var boxes = {{}};
    names.forEach(function(name) {{ boxes[name] = calcBox(largeGroups[name], pad); }});
    for (var iter = 0; iter < 8; iter++) {{
      var conflict = false;
      for (var i = 0; i < names.length; i++) {{
        for (var j = i + 1; j < names.length; j++) {{
          var a = boxes[names[i]], b = boxes[names[j]];
          if (a && b && overlaps(a, b)) {{
            conflict = true;
            var shrink = Math.max(pad - (iter + 1) * 6, 5);
            boxes[names[i]] = calcBox(largeGroups[names[i]], shrink);
            boxes[names[j]] = calcBox(largeGroups[names[j]], shrink);
          }}
        }}
      }}
      if (!conflict) break;
    }}
    names.forEach(function(name) {{
      var box = boxes[name];
      if (!box) return;
      ctx.save();
      ctx.strokeStyle = largeColors[name];
      ctx.fillStyle = largeColors[name] + "22";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.rect(box.minX, box.minY, box.maxX - box.minX, box.maxY - box.minY);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = largeColors[name];
      ctx.font = "bold 16px sans-serif";
      ctx.fillText(name, box.minX + 8, box.minY + 20);
      ctx.restore();
    }});
  }});
}});
</script>
"""
    html = html.replace("</body>", extra + "</body>")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
