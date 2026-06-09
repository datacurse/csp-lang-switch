#!/usr/bin/env python3
"""
csp5.py
=======
Parser and serializer for the Clip Studio Paint 5 binary resource file format
(the GUID-named files under langs/<language>/ui/, e.g.
742DEA58-ED6B-4402-BC11-20DFC6D08040).

Format -- all integers are unsigned 32-bit BIG-ENDIAN:

  * Top-level container: a 40-byte header =
        uint32 block_count (= 3)
        3 x (uint32 id, uint32 offset, uint32 length)
    `offset` is an ABSOLUTE FILE OFFSET. Blocks are contiguous after the header.
        block id=1 : string data  (a recursively nested container)
        block id=2 : index table  (language-independent -> copied verbatim)
        block id=3 : footer        (language-independent -> copied verbatim)

  * Block 1 is built from one repeating primitive, a DIRECTORY:
        uint32 count
        count x (uint32 id, uint32 offset, uint32 length)
        ... child data follows immediately, with no gaps or padding ...
    Entry offsets are absolute file offsets and chain perfectly:
        entry[0].offset   == <node start> + 4 + 12*count
        entry[n+1].offset == entry[n].offset + entry[n].length
        the last entry ends exactly at the node's end.

  * Strings are stored as [uint32 byte_length][UTF-8 bytes], no terminator.

The parser models block 1 as a tree of nodes that store NO absolute offsets;
serialize() recomputes every offset and length from child sizes. Therefore
serialize(parse(f)) == f proves the structural model is correct and complete.

This follows the verified model in CSP5_format_spec.md as corrected by the
project plan: offsets are file-absolute, there is no secondary structure
between a directory and its data, and a directory's first uint32 is exactly
its entry count.

No external dependencies (standard library only).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field


class CSPFormatError(Exception):
    """Raised when a file does not match the expected CSP5 resource format."""


# ----------------------------------------------------------------------
# uint32 big-endian helpers
# ----------------------------------------------------------------------
def u32(n: int) -> bytes:
    """Encode an int as a big-endian unsigned 32-bit value."""
    if not 0 <= n <= 0xFFFFFFFF:
        raise CSPFormatError(f"value out of uint32 range: {n}")
    return struct.pack(">I", n)


def read_u32(buf: bytes, off: int) -> int:
    """Decode a big-endian unsigned 32-bit value at `off`."""
    if off < 0 or off + 4 > len(buf):
        raise CSPFormatError(f"uint32 read out of bounds at offset {off}")
    return struct.unpack_from(">I", buf, off)[0]


# ----------------------------------------------------------------------
# Node tree (block 1).  Nodes store structure only -- never absolute offsets.
# ----------------------------------------------------------------------
@dataclass
class DirectoryNode:
    """A directory: an ordered list of (entry_id, child) pairs."""
    children: list[tuple[int, "Node"]] = field(default_factory=list)


@dataclass
class StringStreamNode:
    """A leaf holding one or more length-prefixed UTF-8 string records."""
    strings: list[str] = field(default_factory=list)


@dataclass
class BlobNode:
    """A leaf of opaque bytes (PNG assets, self-length sub-containers, ...)."""
    data: bytes = b""


Node = DirectoryNode | StringStreamNode | BlobNode


@dataclass
class Container:
    """A whole CSP5 resource file."""
    raw_header: bytes        # original 40-byte header (informational only)
    block1: Node             # parsed tree of the string-data block
    block2: bytes            # index table, copied verbatim
    block3: bytes            # footer, copied verbatim


# ----------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------
# A directory count larger than this cannot fit in any real file; the bound
# rejects garbage fast and guards against absurd allocations.
_MAX_DIR_COUNT = 1 << 24


def _looks_like_directory(
    data: bytes, off: int, end: int
) -> list[tuple[int, int, int]] | None:
    """Return the entry list if [off, end) is a valid directory, else None.

    A valid directory has `count` entries that chain with no gaps and cover
    [off + 4 + 12*count, end) exactly.
    """
    if end - off < 4 + 12:                  # too small for a 1-entry directory
        return None
    count = read_u32(data, off)
    if count == 0 or count > _MAX_DIR_COUNT:
        return None
    array_end = off + 4 + 12 * count
    if array_end > end:
        return None
    entries: list[tuple[int, int, int]] = []
    cursor = array_end                      # where the first child must begin
    for i in range(count):
        base = off + 4 + 12 * i
        eid = read_u32(data, base)
        eoff = read_u32(data, base + 4)
        elen = read_u32(data, base + 8)
        if eoff != cursor:                  # entries must chain with no gaps
            return None
        if elen > end - cursor:             # child must stay within the node
            return None
        entries.append((eid, eoff, elen))
        cursor += elen
    if cursor != end:                       # entries must cover the node exactly
        return None
    return entries


def _looks_like_string_stream(data: bytes, off: int, end: int) -> list[str] | None:
    """Return the decoded strings if [off, end) is a valid string stream."""
    if end - off < 4:
        return None
    strings: list[str] = []
    pos = off
    while pos < end:
        if pos + 4 > end:
            return None
        ln = read_u32(data, pos)
        if pos + 4 + ln > end:
            return None
        chunk = data[pos + 4:pos + 4 + ln]
        try:
            strings.append(chunk.decode("utf-8"))
        except UnicodeDecodeError:
            return None
        pos += 4 + ln
    if pos != end or not strings:
        return None
    return strings


def _parse_node(data: bytes, off: int, end: int) -> Node:
    """Classify and parse the byte range [off, end) of block 1.

    Directory first, then string stream, then opaque blob.
    """
    if end - off < 4:
        return BlobNode(data[off:end])

    entries = _looks_like_directory(data, off, end)
    if entries is not None:
        node = DirectoryNode()
        for eid, eoff, elen in entries:
            node.children.append((eid, _parse_node(data, eoff, eoff + elen)))
        return node

    strings = _looks_like_string_stream(data, off, end)
    if strings is not None:
        return StringStreamNode(strings)

    return BlobNode(data[off:end])


def parse(data: bytes) -> Container:
    """Parse a CSP5 resource file (bytes) into a Container."""
    if len(data) < 40:
        raise CSPFormatError(
            f"file too small to hold a 40-byte header ({len(data)} bytes)")

    block_count = read_u32(data, 0)
    if block_count != 3:
        raise CSPFormatError(f"expected block_count=3, got {block_count}")

    blocks: list[tuple[int, int, int]] = []
    for i in range(3):
        base = 4 + 12 * i
        blocks.append((read_u32(data, base),
                       read_u32(data, base + 4),
                       read_u32(data, base + 8)))

    # Blocks must be ids 1, 2, 3 in order, contiguous right after the 40-byte
    # header, and end exactly at end-of-file.
    expect_off = 40
    for idx, (bid, boff, blen) in enumerate(blocks):
        if bid != idx + 1:
            raise CSPFormatError(f"block {idx}: expected id={idx + 1}, got {bid}")
        if boff != expect_off:
            raise CSPFormatError(
                f"block id={bid}: expected offset {expect_off}, got {boff}")
        if boff + blen > len(data):
            raise CSPFormatError(f"block id={bid}: runs past end of file")
        expect_off += blen
    if expect_off != len(data):
        raise CSPFormatError(
            f"blocks do not end at EOF (blocks end={expect_off}, file={len(data)})")

    _, off1, len1 = blocks[0]
    _, off2, len2 = blocks[1]
    _, off3, len3 = blocks[2]

    return Container(
        raw_header=data[:40],
        block1=_parse_node(data, off1, off1 + len1),
        block2=data[off2:off2 + len2],
        block3=data[off3:off3 + len3],
    )


# ----------------------------------------------------------------------
# Serialization -- recomputes every offset and length from child sizes.
# ----------------------------------------------------------------------
def node_size(node: Node) -> int:
    """Total serialized byte length of a block-1 node."""
    if isinstance(node, StringStreamNode):
        return sum(4 + len(s.encode("utf-8")) for s in node.strings)
    if isinstance(node, BlobNode):
        return len(node.data)
    if isinstance(node, DirectoryNode):
        return (4 + 12 * len(node.children)
                + sum(node_size(c) for _, c in node.children))
    raise CSPFormatError(f"unknown node type: {type(node).__name__}")


def _emit(node: Node, out: bytearray) -> None:
    """Append `node`'s bytes to `out`. Block 1 begins at file offset 40."""
    if isinstance(node, StringStreamNode):
        for s in node.strings:
            b = s.encode("utf-8")
            out += u32(len(b))
            out += b
        return
    if isinstance(node, BlobNode):
        out += node.data
        return
    if isinstance(node, DirectoryNode):
        n = len(node.children)
        node_start = 40 + len(out)          # absolute file offset of this node
        out += u32(n)
        cursor = node_start + 4 + 12 * n    # where the first child begins
        for cid, child in node.children:
            sz = node_size(child)
            out += u32(cid) + u32(cursor) + u32(sz)
            cursor += sz
        for _, child in node.children:
            _emit(child, out)
        return
    raise CSPFormatError(f"unknown node type: {type(node).__name__}")


def serialize(container: Container) -> bytes:
    """Serialize a Container back to bytes (the inverse of parse)."""
    b1 = bytearray()
    _emit(container.block1, b1)
    b1 = bytes(b1)

    off1 = 40
    off2 = off1 + len(b1)
    off3 = off2 + len(container.block2)

    header = bytearray()
    header += u32(3)
    header += u32(1) + u32(off1) + u32(len(b1))
    header += u32(2) + u32(off2) + u32(len(container.block2))
    header += u32(3) + u32(off3) + u32(len(container.block3))

    return bytes(header) + b1 + container.block2 + container.block3


# ----------------------------------------------------------------------
# Tree traversal helpers (used by roundtrip.py and repack.py)
# ----------------------------------------------------------------------
def iter_string_nodes(node: Node, path: tuple[int, ...] = ()):
    """Yield (path, StringStreamNode) for every string leaf, depth-first.

    `path` is the tuple of entry IDs from the root to the leaf -- a stable
    key across languages (the tree shape is identical in every language).
    """
    if isinstance(node, DirectoryNode):
        for cid, child in node.children:
            yield from iter_string_nodes(child, path + (cid,))
    elif isinstance(node, StringStreamNode):
        yield path, node


def tree_stats(node: Node) -> dict[str, int]:
    """Count directories, string leaves, blob leaves and total string records."""
    stats = {"directories": 0, "string_leaves": 0, "blob_leaves": 0,
             "string_records": 0, "max_depth": 0}

    def walk(n: Node, depth: int) -> None:
        stats["max_depth"] = max(stats["max_depth"], depth)
        if isinstance(n, DirectoryNode):
            stats["directories"] += 1
            for _, child in n.children:
                walk(child, depth + 1)
        elif isinstance(n, StringStreamNode):
            stats["string_leaves"] += 1
            stats["string_records"] += len(n.strings)
        elif isinstance(n, BlobNode):
            stats["blob_leaves"] += 1

    walk(node, 0)
    return stats
