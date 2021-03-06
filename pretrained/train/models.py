import math
import torch
import torch.nn.functional as F
from torch import nn
from torch.autograd import Variable
from torch.nn import Parameter


class Bottleneck(nn.Module):
    """
    Attributes:
    ------ conv1x1    -> bn -> prelu
    |   -> dw_conv3x3 -> bn -> prelu
    |   -> conv1x1    -> bn ---------->
    ---------------------------------->
    """
    def __init__(self, inp, oup, stride, expansion):
        super(Bottleneck, self).__init__()
        self.connect = stride == 1 and inp == oup
        #
        self.conv = nn.Sequential(
            # pw
            nn.Conv2d(inp, inp * expansion, 1, 1, 0, bias=False),
            nn.BatchNorm2d(inp * expansion),
            nn.PReLU(inp * expansion),
            # nn.ReLU(inplace=True),

            # dw
            nn.Conv2d(inp * expansion, inp * expansion, 3, stride,
                      1, groups=inp * expansion, bias=False),
            nn.BatchNorm2d(inp * expansion),
            nn.PReLU(inp * expansion),
            # nn.ReLU(inplace=True),

            # pw-linear
            nn.Conv2d(inp * expansion, oup, 1, 1, 0, bias=False),
            nn.BatchNorm2d(oup),
        )

    def forward(self, x):
        if self.connect:
            return x + self.conv(x)
        else:
            return self.conv(x)


class ConvBlock(nn.Module):
    """
    Attributes:
        conv/dw_conv kxk -> bn -> prelu/linear
    """
    def __init__(self, inp, oup, k, s, p, dw=False, linear=False):
        super(ConvBlock, self).__init__()
        self.linear = linear
        if dw:
            self.conv = nn.Conv2d(inp, oup, k, s, p, groups=inp, bias=False)
        else:
            self.conv = nn.Conv2d(inp, oup, k, s, p, bias=False)
        self.bn = nn.BatchNorm2d(oup)
        if not linear:
            self.prelu = nn.PReLU(oup)

    def forward(self, x):
        x = self.conv(x)
        x = self.bn(x)
        if self.linear:
            return x
        else:
            return self.prelu(x)


Mobilefacenet_bottleneck_setting = [
    # t, c , n ,s
    [2, 64, 5, 2],
    [4, 128, 1, 2],
    [2, 128, 6, 1],
    [4, 128, 1, 2],
    [2, 128, 2, 1]
]

Mobilenetv2_bottleneck_setting = [
    # t, c, n, s
    [1, 16, 1, 1],
    [6, 24, 2, 2],
    [6, 32, 3, 2],
    [6, 64, 4, 2],
    [6, 96, 3, 1],
    [6, 160, 3, 2],
    [6, 320, 1, 1],
]


class MobileFacenet(nn.Module):
    """
    Attributes:
           conv1    =    conv3x3 -> bn -> prelu
        -> dw_conv1 = dw_conv3x3 -> bn -> prelu
        -> blocks   = 
            -> bottlenet = conv1x1 -> bn -> prelu -> dw_conv3x3 -> bn -> prelu -> conv1x1 -> bn -> prelu
            -> bottlenet = conv1x1 -> bn -> prelu -> dw_conv3x3 -> bn -> prelu -> conv1x1 -> bn -> prelu
            -> ...
            -> bottlenet = conv1x1 -> bn -> prelu -> dw_conv3x3 -> bn -> prelu -> conv1x1 -> bn -> prelu
        -> conv2    =    conv1x1 -> bn -> prelu
        -> linear7  = dw_convGLB -> bn
        -> linear1  =    conv1x1 -> bn
    """
    def __init__(self, num_classes, facesize=(112, 96), bottleneck_setting=Mobilefacenet_bottleneck_setting):
        super(MobileFacenet, self).__init__()
        self.num_classes = num_classes
        self.h, self.w = facesize
        self.conv1 = ConvBlock(3, 64, 3, 2, 1)
        self.dw_conv1 = ConvBlock(64, 64, 3, 1, 1, dw=True)
        self.inplanes = 64
        block = Bottleneck
        self.blocks = self._make_layer(block, bottleneck_setting)
        self.conv2 = ConvBlock(128, 512, 1, 1, 0)
        self.linear7 = ConvBlock(
            512, 512, (self.h // 16, self.w // 16), 1, 0, dw=True, linear=True)
        self.linear1 = ConvBlock(512, 128, 1, 1, 0, linear=True)
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                n = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
                m.weight.data.normal_(0, math.sqrt(2. / n))
            elif isinstance(m, nn.BatchNorm2d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()
        self.weight = Parameter(torch.Tensor(num_classes, 128))
        nn.init.xavier_uniform_(self.weight)

    def _make_layer(self, block, setting):
        layers = []
        for t, c, n, s in setting:
            for i in range(n):
                if i == 0:
                    layers.append(block(self.inplanes, c, s, t))
                else:
                    layers.append(block(self.inplanes, c, 1, t))
                self.inplanes = c

        return nn.Sequential(*layers)

    def get_feature(self, x):
        x = self.conv1(x)
        x = self.dw_conv1(x)
        x = self.blocks(x)
        x = self.conv2(x)
        x = self.linear7(x)
        x = self.linear1(x)
        x = x.view(x.size(0), -1)
        return x

    def forward(self, x):
        x = self.get_feature(x)
        cosine = F.linear(F.normalize(x), F.normalize(self.weight))
        return cosine



class MobileFacenetUnsupervised(nn.Module):
    """
    Attributes:
           conv1    =    conv3x3 -> bn -> prelu
        -> dw_conv1 = dw_conv3x3 -> bn -> prelu
        -> blocks   = 
            -> bottlenet = conv1x1 -> bn -> prelu -> dw_conv3x3 -> bn -> prelu -> conv1x1 -> bn -> prelu
            -> bottlenet = conv1x1 -> bn -> prelu -> dw_conv3x3 -> bn -> prelu -> conv1x1 -> bn -> prelu
            -> ...
            -> bottlenet = conv1x1 -> bn -> prelu -> dw_conv3x3 -> bn -> prelu -> conv1x1 -> bn -> prelu
        -> conv2    =    conv1x1 -> bn -> prelu
        -> linear7  = dw_convGLB -> bn
        -> linear1  =    conv1x1 -> bn
    """
    def __init__(self, num_classes, facesize=(112, 96), bottleneck_setting=Mobilefacenet_bottleneck_setting):
        super(MobileFacenetUnsupervised, self).__init__()
        
        self.num_classes = num_classes
        self.h, self.w = facesize
        self.conv1 = ConvBlock(3, 64, 3, 2, 1)
        self.dw_conv1 = ConvBlock(64, 64, 3, 1, 1, dw=True)
        self.inplanes = 64
        block = Bottleneck
        self.blocks = self._make_layer(block, bottleneck_setting)
        self.conv2 = ConvBlock(128, 512, 1, 1, 0)
        self.linear7 = ConvBlock(
            512, 512, (self.h // 16, self.w // 16), 1, 0, dw=True, linear=True)
        self.linear1 = ConvBlock(512, 128, 1, 1, 0, linear=True)
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                n = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
                m.weight.data.normal_(0, math.sqrt(2. / n))
            elif isinstance(m, nn.BatchNorm2d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()

    def _make_layer(self, block, setting):
        layers = []
        for t, c, n, s in setting:
            for i in range(n):
                if i == 0:
                    layers.append(block(self.inplanes, c, s, t))
                else:
                    layers.append(block(self.inplanes, c, 1, t))
                self.inplanes = c

        return nn.Sequential(*layers)

    def forward(self, x):

        x = self.conv1(x)
        x = self.dw_conv1(x)
        x = self.blocks(x)
        x = self.conv2(x)
        x = self.linear7(x)
        x = self.linear1(x)
        x = x.view(x.size(0), -1)   # N * 128

        return x


if __name__ == "__main__":
    from torchstat import stat
    stat(MobileFacenet(1000), (3, 112, 96))
